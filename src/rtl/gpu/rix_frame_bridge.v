// SPDX-License-Identifier: GPL-3.0-or-later
// One bounded burst outstanding. Cache the immutable PS pixels once, then
// expand the same cache into raw scanout and (when leased) snapshot memory.
// Aligned power-of-two bursts never cross a 4 KiB boundary. AW/W independent.
module rix_frame_bridge #(
    parameter WIDTH=400, HEIGHT=240,
    parameter PS_GFX_BASE=32'h0, // Must be set from a verified board memory map.
    parameter SLOT0=32'h0, SLOT1=32'h00100000,
    parameter TIMEOUT_CYCLES=100000000,
    parameter SNAPSHOT_BASE=32'h21400000,
    parameter BURST_BEATS=16
)(
    input wire clk,rst,enable,mig_ready,lcd_running,
    input wire swap_fb,
    input wire [31:0] fb_addr,
    input wire [19:0] fb_size,
    output reg fb_swapped,
    input wire front_slot,
    output reg present_valid,
    output reg present_slot,
    output reg [31:0] frame_id,
    input wire present_ack,
    input wire [31:0] presented_id,
    output reg copy_done,fault,
    // Valid with copy_done. PS color slots are aligned to 1 MiB; the final
    // read stays inside the accepted slot, even if upstream fb_addr changes.
    output wire [31:0] completed_source_base,
    input wire snapshot_pending,
    output wire snapshot_start,snapshot_error,
    output reg snapshot_done,
    output reg [7:0] first_error,
    output reg [31:0] swap_count,copy_count,present_count,read_errors,write_errors,timeouts,
    output reg [31:0] m_ps_araddr,
    output wire [7:0] m_ps_arlen,
    output wire [2:0] m_ps_arsize,
    output wire [1:0] m_ps_arburst,
    output wire m_ps_arvalid,
    input wire m_ps_arready,
    input wire [63:0] m_ps_rdata,
    input wire [1:0] m_ps_rresp,
    input wire m_ps_rlast,m_ps_rvalid,
    output wire m_ps_rready,
    output reg [31:0] m_pl_awaddr,
    output wire [7:0] m_pl_awlen,
    output wire [2:0] m_pl_awsize,
    output wire [1:0] m_pl_awburst,
    output wire m_pl_awvalid,
    input wire m_pl_awready,
    output wire [127:0] m_pl_wdata,
    output wire [15:0] m_pl_wstrb,
    output wire m_pl_wlast,m_pl_wvalid,
    input wire m_pl_wready,
    input wire [1:0] m_pl_bresp,
    input wire m_pl_bvalid,
    output wire m_pl_bready
);
    localparam IDLE=0,AR=1,R=2,WRITE=3,B=4,PRESENT=5,RELEASE=6,STOP=7,PREFETCH=8;
    localparam PIXELS=WIDTH*HEIGHT;
    reg [3:0] state;
    reg aw_done,w_done;
    reg snapshot_copy,snapshot_word;
    reg [31:0] raw_address,snapshot_offset;
    reg [31:0] remaining,timer;
    reg [4:0] burst_beats,received;
    reg [3:0] write_position;
    (* ram_style="block" *) reg [63:0] burst_buffer[0:15];
    reg [63:0] buffered_data;
    wire ar_fire=m_ps_arvalid&&m_ps_arready;
    wire r_fire=m_ps_rvalid&&m_ps_rready;
    wire aw_fire=m_pl_awvalid&&m_pl_awready;
    wire w_fire=m_pl_wvalid&&m_pl_wready;
    wire b_fire=m_pl_bvalid&&m_pl_bready;
    wire progress=ar_fire||r_fire||aw_fire||w_fire||b_fire||present_ack;
    wire valid_config=PIXELS>0&&BURST_BEATS>=1&&BURST_BEATS<=16&&(BURST_BEATS&(BURST_BEATS-1))==0&&
        SLOT0[11:0]==0&&SLOT1[11:0]==0&&SNAPSHOT_BASE[11:0]==0;
    wire valid_source=valid_config&&(PS_GFX_BASE[19:0]==0)&&(PIXELS*2<=1048576)&&(fb_addr==PS_GFX_BASE || fb_addr==PS_GFX_BASE+32'h00100000 || fb_addr==PS_GFX_BASE+32'h00200000);
    wire last_write=write_position==burst_beats-1;
    wire bad_read=m_ps_rresp!=0||m_ps_rlast!=(received+1==burst_beats)||received>=burst_beats;
    wire buffer_read_enable=!rst&&(state==PREFETCH||(state==WRITE&&w_fire&&!last_write));
    wire [3:0] buffer_read_address=state==PREFETCH?4'd0:write_position+4'd1;
    function [4:0] choose_burst;
        input [31:0] words;
        begin choose_burst=words<BURST_BEATS?words[4:0]:BURST_BEATS;end
    endfunction
    assign completed_source_base={m_ps_araddr[31:20],20'b0};
    assign snapshot_start=state==IDLE&&swap_fb&&enable&&valid_source&&
        fb_size==PIXELS&&PIXELS%4==0&&mig_ready&&lcd_running&&snapshot_pending;
    assign snapshot_error=snapshot_copy&&fault;
    assign m_ps_arlen=burst_beats-1;
    assign m_ps_arsize=3;
    assign m_ps_arburst=1;
    assign m_ps_arvalid=state==AR;
    assign m_ps_rready=state==R;
    assign m_pl_awlen=burst_beats-1;
    assign m_pl_awsize=4;
    assign m_pl_awburst=1;
    assign m_pl_awvalid=state==WRITE&&!aw_done;
    assign m_pl_wstrb=16'hffff;
    assign m_pl_wlast=last_write;
    assign m_pl_wvalid=state==WRITE&&!w_done;
    assign m_pl_bready=state==B;
    function [31:0] expand;
        input [15:0] p;
        begin expand={8'b0,p[15:11],p[15:13],p[10:5],p[10:9],p[4:0],p[4:2]};end
    endfunction
    assign m_pl_wdata={expand(buffered_data[63:48]),expand(buffered_data[47:32]),expand(buffered_data[31:16]),expand(buffered_data[15:0])};
    // One explicit read address is essential for BRAM inference. Data remains
    // stable through W stalls, and the cache is not reused until the last B.
    always @(posedge clk) begin
        if(!rst&&state==R&&r_fire&&!fault&&!bad_read)burst_buffer[received[3:0]]<=m_ps_rdata;
        if(buffer_read_enable)buffered_data<=burst_buffer[buffer_read_address];
    end
    always @(posedge clk) begin
        if(rst) begin
            state<=IDLE;fb_swapped<=0;present_valid<=0;present_slot<=0;frame_id<=0;
            copy_done<=0;fault<=0;first_error<=0;swap_count<=0;copy_count<=0;present_count<=0;
            read_errors<=0;write_errors<=0;timeouts<=0;timer<=0;remaining<=0;
            aw_done<=0;w_done<=0;m_ps_araddr<=0;m_pl_awaddr<=0;
            burst_beats<=1;received<=0;write_position<=0;
            snapshot_copy<=0;snapshot_word<=0;raw_address<=0;snapshot_offset<=0;snapshot_done<=0;
        end else begin
            fb_swapped<=0;copy_done<=0;snapshot_done<=0;
            if(state==IDLE||state==RELEASE||state==STOP||progress) timer<=0;
            else if(timer<TIMEOUT_CYCLES) timer<=timer+1;
            if(timer==TIMEOUT_CYCLES-1&&!progress&&!fault) begin
                fault<=1;first_error<=8'd4;timeouts<=timeouts+1;
                // Accepted AXI transactions remain live until responses drain.
                // External recovery must reset GPU, bridge and AXI paths together.
                if(state==PRESENT) begin present_valid<=0;state<=STOP;end
            end
            case(state)
            IDLE: if(swap_fb&&enable) begin
                swap_count<=swap_count+1;frame_id<=frame_id+1;
                if(!valid_source||fb_size!=PIXELS||PIXELS%4!=0||!mig_ready||!lcd_running) begin
                    fault<=1;first_error<=1;state<=STOP;
                end else begin
                    m_ps_araddr<=fb_addr;present_slot<=!front_slot;
                    m_pl_awaddr<=front_slot?SLOT0:SLOT1;
                    raw_address<=front_slot?SLOT0:SLOT1;
                    snapshot_copy<=snapshot_pending;snapshot_word<=0;snapshot_offset<=0;
                    remaining<=PIXELS/4;burst_beats<=choose_burst(PIXELS/4);received<=0;state<=AR;
                end
            end
            AR: if(ar_fire) state<=R;
            R: if(r_fire) begin
                if(received<31)received<=received+1;
                if(bad_read) begin
                    read_errors<=read_errors+1;fault<=1;
                    if(!fault) first_error<=2;
                    // A malformed burst must still drain through RLAST.
                    if(m_ps_rlast) state<=STOP;
                end else if(m_ps_rlast) begin
                    if(fault)state<=STOP;
                    else begin aw_done<=0;w_done<=0;write_position<=0;state<=PREFETCH;end
                end
            end
            PREFETCH: state<=WRITE;
            WRITE: begin
                if(aw_fire) aw_done<=1;
                if(w_fire)begin
                    if(last_write)w_done<=1;
                    else write_position<=write_position+1;
                end
                if((aw_done||aw_fire)&&(w_done||(w_fire&&last_write))) state<=B;
            end
            B: if(b_fire) begin
                if(m_pl_bresp!=0) begin
                    write_errors<=write_errors+1;fault<=1;
                    if(!fault) first_error<=3;
                    state<=STOP;
                end else if(fault) state<=STOP;
                else if(snapshot_copy&&!snapshot_word) begin
                    // Duplicate the exact pixels committed to raw scanout, rather
                    // than rereading a PS slot which the renderer can reuse.
                    m_pl_awaddr<=SNAPSHOT_BASE+snapshot_offset;
                    snapshot_word<=1;aw_done<=0;w_done<=0;write_position<=0;state<=PREFETCH;
                end
                else if(remaining==burst_beats) begin
                    copy_done<=1;copy_count<=copy_count+1;present_valid<=1;state<=PRESENT;
                    snapshot_done<=snapshot_copy;
                end else begin
                    remaining<=remaining-burst_beats;burst_beats<=choose_burst(remaining-burst_beats);received<=0;
                    m_ps_araddr<=m_ps_araddr+(burst_beats<<3);
                    raw_address<=raw_address+(burst_beats<<4);m_pl_awaddr<=raw_address+(burst_beats<<4);
                    snapshot_offset<=snapshot_offset+(burst_beats<<4);snapshot_word<=0;state<=AR;
                end
            end
            PRESENT: if(present_ack&&!fault) begin
                present_valid<=0;
                if(presented_id!=frame_id) begin fault<=1;first_error<=5;state<=STOP;end
                else begin fb_swapped<=1;present_count<=present_count+1;state<=RELEASE;end
            end
            RELEASE: if(!swap_fb) state<=IDLE;
            STOP: present_valid<=0;
            endcase
        end
    end
endmodule
