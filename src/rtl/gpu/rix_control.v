// SPDX-License-Identifier: GPL-3.0-or-later
// AXI-Lite: independent AW/W capture, stable responses, explicit snapshot.
module rix_control #(parameter CONFIG_HASH=0,PS_GFX_BASE=0)(
    input wire clk,rst,
    input wire [31:0] live_status,
    input wire [383:0] live_counters,
    output reg enable,
    output reg [31:0] post_control,
    input wire [31:0] post_active,last_fb_addr,
    output reg capture_req,output reg [12:0] capture_addr,
    input wire capture_ack,input wire [15:0] capture_data,
    output reg snapshot_request,snapshot_release,
    output reg [31:0] snapshot_command_token,
    input wire [31:0] snapshot_status,snapshot_token,snapshot_frame_id,snapshot_expired_count,
    input wire [7:0] s_axi_awaddr,
    input wire s_axi_awvalid,
    output wire s_axi_awready,
    input wire [31:0] s_axi_wdata,
    input wire [3:0] s_axi_wstrb,
    input wire s_axi_wvalid,
    output wire s_axi_wready,
    output reg [1:0] s_axi_bresp,
    output reg s_axi_bvalid,
    input wire s_axi_bready,
    input wire [7:0] s_axi_araddr,
    input wire s_axi_arvalid,
    output wire s_axi_arready,
    output reg [31:0] s_axi_rdata,
    output reg [1:0] s_axi_rresp,
    output reg s_axi_rvalid,
    input wire s_axi_rready
);
    reg aw_held,w_held;
    reg [7:0] awaddr;
    reg [31:0] wdata;
    reg [3:0] wstrb;
    reg [383:0] counters;
    assign s_axi_awready=!aw_held&&!s_axi_bvalid;
    assign s_axi_wready=!w_held&&!s_axi_bvalid;
    assign s_axi_arready=!s_axi_rvalid;
    always @(posedge clk) begin
        if(rst) begin
            enable<=0;post_control<=0;capture_req<=0;capture_addr<=0;aw_held<=0;w_held<=0;awaddr<=0;wdata<=0;wstrb<=0;counters<=0;
            s_axi_bvalid<=0;s_axi_bresp<=0;s_axi_rvalid<=0;s_axi_rdata<=0;s_axi_rresp<=0;
            snapshot_request<=0;snapshot_release<=0;snapshot_command_token<=0;
        end else begin
            snapshot_request<=0;snapshot_release<=0;
            if(!live_status[0]||!live_status[1]||live_status[2]) enable<=0;
            if(s_axi_awvalid&&s_axi_awready) begin aw_held<=1;awaddr<=s_axi_awaddr;end
            if(s_axi_wvalid&&s_axi_wready) begin w_held<=1;wdata<=s_axi_wdata;wstrb<=s_axi_wstrb;end
            if(s_axi_bvalid&&s_axi_bready) s_axi_bvalid<=0;
            if(aw_held&&w_held&&!s_axi_bvalid) begin
                aw_held<=0;w_held<=0;s_axi_bvalid<=1;s_axi_bresp<=0;
                case(awaddr)
                8'h04: if(wstrb[0]) begin
                    if(wdata[0]&&(!live_status[0]||!live_status[1]||live_status[2])) s_axi_bresp<=2;
                    else enable<=wdata[0];
                end
                8'h40: if(wstrb[0]&&wdata[0]) counters<=live_counters;
                8'h54: begin
                    if(wstrb!=4'hf || (wdata&32'hfffffccC)!=0) s_axi_bresp<=2;
                    else post_control<=wdata;
                end
                8'h64: if(wstrb[0]&&wdata[0]) begin
                    if(capture_req!=capture_ack) s_axi_bresp<=2;
                    else capture_req<=!capture_req;
                end
                8'h6c: if(wstrb==4'hf&&wdata<6000) capture_addr<=wdata[12:0];else s_axi_bresp<=2;
                8'h78: begin
                    if(wstrb!=4'hf||wdata==0||wdata==snapshot_token||snapshot_status[1:0]!=0||
                       !live_status[0]||!live_status[1]||live_status[2]) s_axi_bresp<=2;
                    else begin snapshot_command_token<=wdata;snapshot_request<=1;end
                end
                8'h80: begin
                    if(wstrb!=4'hf||wdata==0||wdata!=snapshot_token||snapshot_status[1:0]==0) s_axi_bresp<=2;
                    else begin snapshot_command_token<=wdata;snapshot_release<=1;end
                end
                default: s_axi_bresp<=2;
                endcase
            end
            if(s_axi_rvalid&&s_axi_rready) s_axi_rvalid<=0;
            if(s_axi_arvalid&&s_axi_arready) begin
                s_axi_rvalid<=1;s_axi_rresp<=0;s_axi_rdata<=0;
                case(s_axi_araddr)
                8'h00:s_axi_rdata<=32'h52495801;
                8'h04:s_axi_rdata<={31'b0,enable};
                8'h08:s_axi_rdata<=live_status;
                8'h0c:s_axi_rdata<=CONFIG_HASH;
                8'h44:s_axi_rdata<=PS_GFX_BASE;
                8'h48:s_axi_rdata<=32'h02000000;
                8'h50:s_axi_rdata<=32'h50535431;
                8'h54:s_axi_rdata<=post_control;
                8'h58:s_axi_rdata<=post_active;
                8'h5c:s_axi_rdata<=last_fb_addr;
                8'h64:s_axi_rdata<={31'b0,capture_req};
                8'h68:s_axi_rdata<={31'b0,capture_ack};
                8'h6c:s_axi_rdata<={19'b0,capture_addr};
                8'h70:s_axi_rdata<={16'b0,capture_data};
                8'h74:s_axi_rdata<=32'h534e5031; // SNP1 leased snapshot capability
                8'h78:s_axi_rdata<=snapshot_token;
                8'h7c:s_axi_rdata<=snapshot_status;
                8'h80:s_axi_rdata<=snapshot_token;
                8'h84:s_axi_rdata<=snapshot_frame_id;
                8'h88:s_axi_rdata<=32'ha1400000; // PS view of PL 0x21400000
                8'h8c:s_axi_rdata<=snapshot_expired_count;
                8'h90:s_axi_rdata<=32'd384000; // 400x240 XRGB8888
                8'h94:s_axi_rdata<=32'd2000; // per-state lease watchdog, milliseconds
                default: if(s_axi_araddr>=8'h10&&s_axi_araddr<=8'h3c&&s_axi_araddr[1:0]==0)
                    s_axi_rdata<=counters[((s_axi_araddr-8'h10)>>2)*32 +: 32];
                    else s_axi_rresp<=2;
                endcase
            end
        end
    end
endmodule
