// XRGB8888 frame -> 128-bit beat stream. PIXELS must be a multiple of four.
// One outstanding AXI4 read. Abort drains the in-flight transaction; never
// withdraws ARVALID, and cannot recover a slave that never returns RLAST.
module rix_frame_reader_dynamic #(
    parameter [32:0] ADDRESS_LIMIT=33'h040000000,
    parameter integer MAX_BURST_BEATS=256
)(
    input wire clk,rst,start,abort,
    input wire [31:0] frame_base,
    input wire [19:0] frame_pixels,
    output wire idle,
    output reg done,aborted,error,
    output wire [127:0] data,
    output wire valid,
    input wire ready,
    output wire [31:0] m_axi_araddr,
    output wire [7:0] m_axi_arlen,
    output wire [2:0] m_axi_arsize,
    output wire [1:0] m_axi_arburst,
    output wire m_axi_arvalid,
    input wire m_axi_arready,
    input wire [127:0] m_axi_rdata,
    input wire [1:0] m_axi_rresp,
    input wire m_axi_rlast,m_axi_rvalid,
    output wire m_axi_rready
);
    localparam IDLE=0,PLAN=1,ISSUE=2,READ=3,PREFETCH=4,STREAM=5;
    reg [2:0] state;
    reg [31:0] address,remaining;
    // Native 800x480 scanout consumes one pixel per clock. Longer bursts
    // amortize MIG/SmartConnect response latency across up to 1024 pixels.
    reg [8:0] burst_beats,received;
    reg cancelled;
    reg neural_mode;
    // The neural scaler consumes only one source row per five LCD rows.
    // Never leave a MIG read transaction stalled behind that slow consumer:
    // finish the whole neural burst into local BRAM, then serialize it.
    // Native/LR scanout retains its existing direct, high-throughput path.
    (* ram_style="block" *) reg [127:0] burst_buffer[0:255];
    reg [127:0] buffered_data;
    reg [7:0] buffered_position;
    wire [8:0] boundary_beats=9'd256-{1'b0,address[11:4]};
    wire [31:0] available=remaining<MAX_BURST_BEATS ? remaining : MAX_BURST_BEATS;
    wire [32:0] frame_end={1'b0,frame_base}+{13'b0,frame_pixels}*33'd4;
    wire bad_beat=m_axi_rresp!=0 || m_axi_rlast!=(received==burst_beats-1);
    assign idle=state==IDLE;
    assign m_axi_araddr=address;
    assign m_axi_arlen=burst_beats-9'd1;
    assign m_axi_arsize=4;
    assign m_axi_arburst=1;
    assign m_axi_arvalid=state==ISSUE;
    assign data=neural_mode?buffered_data:m_axi_rdata;
    assign valid=(neural_mode ? state==STREAM : state==READ && m_axi_rvalid && !bad_beat) && !cancelled && !abort;
    assign m_axi_rready=state==READ && (neural_mode || cancelled || abort || bad_beat || ready);
    wire buffer_read_enable=!rst && (state==PREFETCH || (state==STREAM && ready && buffered_position<burst_beats-1));
    wire [7:0] buffer_read_address=state==PREFETCH ? 8'd0 : buffered_position+8'd1;
    always @(posedge clk) begin
        if(!rst && state==READ && neural_mode && m_axi_rvalid && m_axi_rready && !cancelled && !abort && !bad_beat)
            burst_buffer[received[7:0]]<=m_axi_rdata;
        if(buffer_read_enable) buffered_data<=burst_buffer[buffer_read_address];
    end
    always @(posedge clk) begin
        if(rst) begin
            state<=IDLE;address<=0;remaining<=0;burst_beats<=0;received<=0;
            cancelled<=0;done<=0;aborted<=0;error<=0;
            neural_mode<=0;buffered_position<=0;
        end else begin
            done<=0;aborted<=0;error<=0;
            if(abort && state!=IDLE) cancelled<=1;
            case(state)
                IDLE: if(start) begin
                    if((frame_pixels!=96000 && frame_pixels!=384000 && frame_pixels!=15360) || frame_base[3:0]!=0 || frame_end>ADDRESS_LIMIT) error<=1;
                    else if(abort) aborted<=1;
                    else begin address<=frame_base;remaining<=frame_pixels/4;cancelled<=0;neural_mode<=frame_pixels==15360;state<=PLAN;end
                end
                PLAN: if(cancelled||abort) begin state<=IDLE;aborted<=1;end
                    else begin
                        burst_beats<=boundary_beats<available ? boundary_beats : available[8:0];
                        received<=0;state<=ISSUE;
                    end
                ISSUE: if(m_axi_arready) state<=READ;
                READ: if(m_axi_rvalid&&m_axi_rready) begin
                    if(bad_beat&&!cancelled&&!abort) begin error<=1;cancelled<=1;end
                    if(m_axi_rlast) begin
                        if(cancelled||abort||bad_beat) begin state<=IDLE;aborted<=1;end
                        else if(neural_mode) state<=PREFETCH;
                        else if(remaining==burst_beats) begin state<=IDLE;done<=1;end
                        else begin
                            remaining<=remaining-burst_beats;
                            address<=address+({23'd0,burst_beats}<<4);state<=PLAN;
                        end
                    end else if(received<511) received<=received+1'b1;
                end
                PREFETCH: if(cancelled||abort) begin state<=IDLE;aborted<=1;end
                    else begin buffered_position<=0;state<=STREAM;end
                STREAM: if(cancelled||abort) begin state<=IDLE;aborted<=1;end
                    else if(ready) begin
                        if(buffered_position==burst_beats-1) begin
                            if(remaining==burst_beats) begin state<=IDLE;done<=1;end
                            else begin
                                remaining<=remaining-burst_beats;
                                address<=address+({23'd0,burst_beats}<<4);state<=PLAN;
                            end
                        end else buffered_position<=buffered_position+1'b1;
                    end
            endcase
        end
    end
endmodule
