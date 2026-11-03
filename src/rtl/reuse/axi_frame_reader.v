// XRGB8888 frame -> 128-bit beat stream. PIXELS must be a multiple of four.
// One outstanding AXI4 read. Abort drains the in-flight transaction; never
// withdraws ARVALID, and cannot recover a slave that never returns RLAST.
module axi_frame_reader #(
    parameter PIXELS=96000,
    parameter [32:0] ADDRESS_LIMIT=33'h040000000
)(
    input wire clk,rst,start,abort,
    input wire [31:0] frame_base,
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
    localparam IDLE=0,PLAN=1,ISSUE=2,READ=3;
    reg [1:0] state;
    reg [31:0] address,remaining;
    reg [4:0] burst_beats,received;
    reg cancelled;
    wire [8:0] boundary_beats=9'd256-{1'b0,address[11:4]};
    wire [31:0] available=remaining<16 ? remaining : 32'd16;
    wire [32:0] frame_end={1'b0,frame_base}+PIXELS*33'd4;
    wire bad_beat=m_axi_rresp!=0 || m_axi_rlast!=(received==burst_beats-1);
    assign idle=state==IDLE;
    assign m_axi_araddr=address;
    assign m_axi_arlen={3'd0,burst_beats}-1'b1;
    assign m_axi_arsize=4;
    assign m_axi_arburst=1;
    assign m_axi_arvalid=state==ISSUE;
    assign data=m_axi_rdata;
    assign valid=state==READ && m_axi_rvalid && !cancelled && !abort && !bad_beat;
    assign m_axi_rready=state==READ && (cancelled || abort || bad_beat || ready);
    always @(posedge clk) begin
        if(rst) begin
            state<=IDLE;address<=0;remaining<=0;burst_beats<=0;received<=0;
            cancelled<=0;done<=0;aborted<=0;error<=0;
        end else begin
            done<=0;aborted<=0;error<=0;
            if(abort && state!=IDLE) cancelled<=1;
            case(state)
                IDLE: if(start) begin
                    if(PIXELS<=0 || PIXELS%4!=0 || frame_base[3:0]!=0 || frame_end>ADDRESS_LIMIT) error<=1;
                    else if(abort) aborted<=1;
                    else begin address<=frame_base;remaining<=PIXELS/4;cancelled<=0;state<=PLAN;end
                end
                PLAN: if(cancelled||abort) begin state<=IDLE;aborted<=1;end
                    else begin
                        burst_beats<=boundary_beats<available ? boundary_beats[4:0] : available[4:0];
                        received<=0;state<=ISSUE;
                    end
                ISSUE: if(m_axi_arready) state<=READ;
                READ: if(m_axi_rvalid&&m_axi_rready) begin
                    if(bad_beat&&!cancelled&&!abort) begin error<=1;cancelled<=1;end
                    if(m_axi_rlast) begin
                        if(cancelled||abort||bad_beat) begin state<=IDLE;aborted<=1;end
                        else if(remaining==burst_beats) begin state<=IDLE;done<=1;end
                        else begin
                            remaining<=remaining-burst_beats;
                            address<=address+({27'd0,burst_beats}<<4);state<=PLAN;
                        end
                    end else if(received<31) received<=received+1'b1;
                end
            endcase
        end
    end
endmodule
