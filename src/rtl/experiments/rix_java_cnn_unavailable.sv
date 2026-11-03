// SPDX-License-Identifier: MIT
// Register-compatible discovery endpoint for the Java-only hardware profile.
// NNS2 identifies the register layout; capability=0 means no CNN engine exists.
module rix_java_cnn_unavailable(
 (* X_INTERFACE_PARAMETER="XIL_INTERFACENAME s_axi_aclk, ASSOCIATED_BUSIF s_axi, ASSOCIATED_RESET s_axi_aresetn" *)
 input wire s_axi_aclk,
 (* X_INTERFACE_PARAMETER="XIL_INTERFACENAME s_axi_aresetn, POLARITY ACTIVE_LOW" *)
 input wire s_axi_aresetn,
 input wire [15:0] s_axi_awaddr,input wire [2:0] s_axi_awprot,
 input wire s_axi_awvalid,output wire s_axi_awready,
 input wire [31:0] s_axi_wdata,input wire [3:0] s_axi_wstrb,
 input wire s_axi_wvalid,output wire s_axi_wready,
 output reg [1:0] s_axi_bresp,output reg s_axi_bvalid,input wire s_axi_bready,
 input wire [15:0] s_axi_araddr,input wire [2:0] s_axi_arprot,
 input wire s_axi_arvalid,output wire s_axi_arready,
 output reg [31:0] s_axi_rdata,output reg [1:0] s_axi_rresp,
 output reg s_axi_rvalid,input wire s_axi_rready
);
 reg aw_held,w_held;
 assign s_axi_awready=!aw_held&&!s_axi_bvalid;
 assign s_axi_wready=!w_held&&!s_axi_bvalid;
 assign s_axi_arready=!s_axi_rvalid;
 always @(posedge s_axi_aclk) begin
  if(!s_axi_aresetn) begin
   aw_held<=0;w_held<=0;s_axi_bvalid<=0;s_axi_bresp<=0;
   s_axi_rvalid<=0;s_axi_rdata<=0;s_axi_rresp<=0;
  end else begin
   if(s_axi_awvalid&&s_axi_awready) aw_held<=1;
   if(s_axi_wvalid&&s_axi_wready) w_held<=1;
   if(aw_held&&w_held&&!s_axi_bvalid) begin
    aw_held<=0;w_held<=0;s_axi_bvalid<=1;s_axi_bresp<=2'b10;
   end
   if(s_axi_bvalid&&s_axi_bready) s_axi_bvalid<=0;
   if(s_axi_rvalid&&s_axi_rready) s_axi_rvalid<=0;
   if(s_axi_arvalid&&s_axi_arready) begin
    s_axi_rvalid<=1;s_axi_rresp<=0;
    case(s_axi_araddr)
     16'h0000:s_axi_rdata<=32'h4e4e5332;
     16'h0048:s_axi_rdata<=32'h4a415630; // JAV0: deliberately unavailable
     default:s_axi_rdata<=0; // shape, capabilities, ABI, ready and completion all absent
    endcase
   end
  end
 end
endmodule
