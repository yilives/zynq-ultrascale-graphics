// SPDX-License-Identifier: MIT
// Experimental control/PIO adapter. The CPU supplies one 160x96 RGB frame;
// ALL three CNN convolution layers execute in rix_cnn_engine on the FPGA.
// Eight-word PIO snapshot window; unchanged convolution arithmetic/core.
// No DMA master, new DDR storage, or additional convolution operators.
module rix_cnn_axi #(
 parameter integer WIDTH=160,HEIGHT=96,NEURAL_SCALE5X=0
)(
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
 reg aw_held,w_held;reg [15:0] aw_address;reg [31:0] w_data;reg [3:0] w_strobe;
 reg soft_reset,cfg_restart,cfg_valid,cfg_commit,start,s_valid,s_last;
 reg [63:0] s_data;
 reg [11:0] cfg_addr;reg [31:0] cfg_data;
 wire cfg_ready,model_valid,busy,fault,s_ready,m_valid,m_last,done;
 wire [63:0] m_data;wire [31:0] compute_cycles;
 reg pop_pending,done_sticky;
 reg [31:0] input_index,output_index,completed_frames;
 // Snapshot window: indexed, non-destructive reads; explicit sequenced ACK.
 // Read ordering/retries and wide CPU loads cannot reorder or consume pixels.
 reg group_enable,group_ready,group_last;
 reg [3:0] group_count;
 reg [31:0] group_sequence;
 reg [31:0] group_words[0:7];
 integer slot;
 wire group_free=!group_ready&&(group_count==0);
 wire control_cfg_ready=cfg_ready&&group_free;
 wire output_valid=group_enable?group_ready:m_valid;
 wire output_last=group_enable?group_last:m_last;
 wire m_ready=group_enable?(!group_ready&&(group_count<8)):
     (pop_pending&&s_axi_rvalid&&s_axi_rready);
 rix_cnn_engine #(.WIDTH(WIDTH),.HEIGHT(HEIGHT)) engine(
  .clk(s_axi_aclk),.rst(!s_axi_aresetn||soft_reset),.cfg_restart(cfg_restart),.cfg_valid(cfg_valid),
  .cfg_commit(cfg_commit),.cfg_addr(cfg_addr),.cfg_data(cfg_data),.cfg_ready(cfg_ready),
  .model_valid(model_valid),.start(start),.busy(busy),.fault(fault),
  .s_data(s_data),.s_valid(s_valid),.s_last(s_last),.s_ready(s_ready),
  .m_data(m_data),.m_valid(m_valid),.m_last(m_last),.m_ready(m_ready),.done(done),.compute_cycles(compute_cycles));
 assign s_axi_awready=!aw_held&&!s_axi_bvalid;
 assign s_axi_wready=!w_held&&!s_axi_bvalid;
 assign s_axi_arready=!s_axi_rvalid;
 always @(posedge s_axi_aclk) begin
  if(!s_axi_aresetn) begin
   aw_held<=0;w_held<=0;s_axi_bvalid<=0;s_axi_bresp<=0;s_axi_rvalid<=0;s_axi_rresp<=0;s_axi_rdata<=0;
   soft_reset<=0;cfg_restart<=0;cfg_valid<=0;cfg_commit<=0;start<=0;s_valid<=0;s_last<=0;
   cfg_addr<=0;cfg_data<=0;s_data<=0;input_index<=0;output_index<=0;completed_frames<=0;pop_pending<=0;done_sticky<=0;
   group_enable<=0;group_ready<=0;group_last<=0;group_count<=0;group_sequence<=0;
   for(slot=0;slot<8;slot=slot+1)group_words[slot]<=0;
  end else begin
   soft_reset<=0;cfg_restart<=0;cfg_valid<=0;cfg_commit<=0;start<=0;s_valid<=0;
   if(done&&!group_enable) begin done_sticky<=1;completed_frames<=completed_frames+1;end
   if(group_enable&&m_valid&&m_ready) begin
    group_words[group_count[2:0]]<={1'b1,fault,m_last,5'd0,(m_data[23:0]^24'h808080)};
    group_count<=group_count+1;
    if(m_last||group_count==7)begin group_ready<=1;group_last<=m_last;end
   end
   if(s_axi_awvalid&&s_axi_awready) begin aw_held<=1;aw_address<=s_axi_awaddr;end
   if(s_axi_wvalid&&s_axi_wready) begin w_held<=1;w_data<=s_axi_wdata;w_strobe<=s_axi_wstrb;end
   if(s_axi_bvalid&&s_axi_bready) s_axi_bvalid<=0;
   if(aw_held&&w_held&&!s_axi_bvalid) begin
    aw_held<=0;w_held<=0;s_axi_bvalid<=1;s_axi_bresp<=0;
    if(w_strobe!=4'hf) s_axi_bresp<=2;
    else case(aw_address)
     16'h0008: case(w_data)
      1: if(busy||!model_valid||fault||!group_free) s_axi_bresp<=2;
         else begin
          start<=1;input_index<=0;output_index<=0;done_sticky<=0;group_sequence<=0;
          group_count<=0;group_ready<=0;group_last<=0;
          for(slot=0;slot<8;slot=slot+1)group_words[slot]<=0;
         end
      2: begin
          soft_reset<=1;input_index<=0;output_index<=0;done_sticky<=0;
          group_enable<=0;group_ready<=0;group_last<=0;group_count<=0;group_sequence<=0;
          for(slot=0;slot<8;slot=slot+1)group_words[slot]<=0;
         end
      4: if(!control_cfg_ready) s_axi_bresp<=2;else cfg_restart<=1;
      8: if(!control_cfg_ready) s_axi_bresp<=2;else cfg_commit<=1;
      default: s_axi_bresp<=2;
     endcase
     16'h0010: if(!s_ready) s_axi_bresp<=2;
      else begin s_data<={40'd0,(w_data[23:0]^24'h808080)};s_valid<=1;s_last<=input_index==WIDTH*HEIGHT-1;input_index<=input_index+1;end
     16'h0020: if(!control_cfg_ready||w_data>4095) s_axi_bresp<=2;else cfg_addr<=w_data[11:0];
     16'h0024: if(!control_cfg_ready) s_axi_bresp<=2;else begin cfg_data<=w_data;cfg_valid<=1;end
     16'h004c:if(busy||!group_free||w_data>1)s_axi_bresp<=2;else group_enable<=w_data[0];
     16'h0050:if(!group_enable||!group_ready||w_data!=group_sequence||s_axi_rvalid)s_axi_bresp<=2;
      else begin
       output_index<=output_index+group_count;group_sequence<=group_sequence+1;
       group_ready<=0;group_count<=0;group_last<=0;
       for(slot=0;slot<8;slot=slot+1)group_words[slot]<=0;
       if(group_last)begin done_sticky<=1;completed_frames<=completed_frames+1;end
      end
     default: s_axi_bresp<=2;
    endcase
   end
   if(s_axi_rvalid&&s_axi_rready) begin
    s_axi_rvalid<=0;pop_pending<=0;
    if(pop_pending) output_index<=output_index+1;
   end
   if(s_axi_arvalid&&s_axi_arready) begin
    s_axi_rvalid<=1;s_axi_rresp<=0;pop_pending<=0;
    case(s_axi_araddr)
     16'h0000:s_axi_rdata<=32'h4e475231; // NGR1: non-destructive output-group adapter.
     16'h0004:s_axi_rdata<={16'(HEIGHT),16'(WIDTH)};
     16'h000c:s_axi_rdata<={25'd0,output_last,done_sticky,fault,model_valid,output_valid,s_ready,busy};
     16'h0018:if(group_enable||!m_valid)begin s_axi_rresp<=2;s_axi_rdata<=0;end
      else begin s_axi_rdata<={8'd0,(m_data[23:0]^24'h808080)};pop_pending<=1;end
     16'h0028:s_axi_rdata<=compute_cycles;
     16'h002c:s_axi_rdata<=completed_frames;
     16'h0030:s_axi_rdata<=input_index;
     16'h0034:s_axi_rdata<=output_index;
     16'h0038:s_axi_rdata<=30*WIDTH*HEIGHT+21*HEIGHT;
     16'h003c:s_axi_rdata<=29|(NEURAL_SCALE5X?2:0); // pipeline, atomic, in-place; 5x only if explicitly paired.
     // Optional nonblocking output port. Invalid reads are OKAY, return valid=0,
     // and never consume a pixel. Valid data is consumed ONLY when this exact
     // AXI R response is accepted, just as with the legacy 0x18 port. A stalled
     // response keeps its sampled flags/data stable and cannot double-pop.
     // bit31 valid, bit30 sticky core fault, bit29 last, bits28:24 zero, RGB[23:0].
     16'h0040:begin
      if(group_enable)begin s_axi_rresp<=2;s_axi_rdata<=0;end
      else if(m_valid) begin s_axi_rdata<={1'b1,fault,m_last,5'd0,(m_data[23:0]^24'h808080)};pop_pending<=1;end
      else s_axi_rdata<={1'b0,fault,30'd0};
     end
     16'h0044:s_axi_rdata<=32'h00040001; // Explicitly incompatible adapter ABI 4.1.
     16'h0048:s_axi_rdata<={group_ready,fault,group_last,25'd0,group_count};
     16'h004c:s_axi_rdata<=group_sequence;
     16'h0050:s_axi_rdata<={31'd0,group_enable};
     default:begin
      // All aliases repeat the same eight-word snapshot. No read pops data.
      if(s_axi_araddr[15:8]==8'h01&&s_axi_araddr[1:0]==0&&group_enable)
       s_axi_rdata<=group_ready?group_words[s_axi_araddr[4:2]]:0;
      else begin s_axi_rresp<=2;s_axi_rdata<=0;end
     end
    endcase
   end
  end
 end
endmodule
