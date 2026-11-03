`timescale 1ns/1ps
module tb_upload;
reg  aclk=0;
reg  resetn=0;
reg  s_cmd_axis_tvalid=0;
wire  s_cmd_axis_tready;
reg  s_cmd_axis_tlast=0;
reg [32 - 1 : 0] s_cmd_axis_tdata=0;
wire  m_cmd_resp_axis_tvalid;
reg  m_cmd_resp_axis_tready=0;
wire  m_cmd_resp_axis_tlast;
wire [32 - 1 : 0] m_cmd_resp_axis_tdata;
wire  swap_fb;
wire  swap_fb_enable_vsync;
wire [32 - 1 : 0] fb_addr;
wire [20 - 1 : 0] fb_size;
reg  fb_swapped=0;
wire [6 - 1 : 0] m_axi_awid;
wire [32 - 1 : 0] m_axi_awaddr;
wire [ 7 : 0] m_axi_awlen;
wire [ 2 : 0] m_axi_awsize;
wire [ 1 : 0] m_axi_awburst;
wire  m_axi_awlock;
wire [ 3 : 0] m_axi_awcache;
wire [ 2 : 0] m_axi_awprot;
wire  m_axi_awvalid;
reg  m_axi_awready=0;
wire [64 - 1 : 0] m_axi_wdata;
wire [8 - 1 : 0] m_axi_wstrb;
wire  m_axi_wlast;
wire  m_axi_wvalid;
reg  m_axi_wready=0;
reg [6 - 1 : 0] m_axi_bid=0;
reg [ 1 : 0] m_axi_bresp=0;
reg  m_axi_bvalid=0;
wire  m_axi_bready;
wire [6 - 1 : 0] m_axi_arid;
wire [32 - 1 : 0] m_axi_araddr;
wire [ 7 : 0] m_axi_arlen;
wire [ 2 : 0] m_axi_arsize;
wire [ 1 : 0] m_axi_arburst;
wire  m_axi_arlock;
wire [ 3 : 0] m_axi_arcache;
wire [ 2 : 0] m_axi_arprot;
wire  m_axi_arvalid;
reg  m_axi_arready=0;
reg [6 - 1 : 0] m_axi_rid=0;
reg [64 - 1 : 0] m_axi_rdata=0;
reg [ 1 : 0] m_axi_rresp=0;
reg  m_axi_rlast=0;
reg  m_axi_rvalid=0;
wire  m_axi_rready;
wire  write_fault;
wire  perfBusy;
wire  perfTriangleRendering;
wire  perfRasterizerStall;
always #5 aclk=~aclk;
RasterIX_IF #(.FRAMEBUFFER_SIZE_IN_PIXEL_LG(15),.FRAMEBUFFER_SUB_PIXEL_WIDTH(5),.FRAMEBUFFER_ENABLE_ALPHA_CHANNEL(0),.ENABLE_DEPTH_BUFFER(1),.ENABLE_STENCIL_BUFFER(0),.TMU_COUNT(1),.MAX_TEXTURE_SIZE(128),.ENABLE_TEXTURE_FILTERING(1),.ENABLE_MIPMAPPING(1),.ENABLE_FOG(1),.RASTERIZER_ENABLE_FLOAT_INTERPOLATION(0),.RASTERIZER_FIXPOINT_PRECISION(25),.SUB_PIXEL_CALC_PRECISION(8),.TEXTURE_PAGE_SIZE(2048),.DATA_WIDTH(64),.ADDR_WIDTH(32),.ID_WIDTH(6)) gpu(.aclk(aclk),.resetn(resetn),.s_cmd_axis_tvalid(s_cmd_axis_tvalid),.s_cmd_axis_tready(s_cmd_axis_tready),.s_cmd_axis_tlast(s_cmd_axis_tlast),.s_cmd_axis_tdata(s_cmd_axis_tdata),.m_cmd_resp_axis_tvalid(m_cmd_resp_axis_tvalid),.m_cmd_resp_axis_tready(m_cmd_resp_axis_tready),.m_cmd_resp_axis_tlast(m_cmd_resp_axis_tlast),.m_cmd_resp_axis_tdata(m_cmd_resp_axis_tdata),.swap_fb(swap_fb),.swap_fb_enable_vsync(swap_fb_enable_vsync),.fb_addr(fb_addr),.fb_size(fb_size),.fb_swapped(fb_swapped),.m_axi_awid(m_axi_awid),.m_axi_awaddr(m_axi_awaddr),.m_axi_awlen(m_axi_awlen),.m_axi_awsize(m_axi_awsize),.m_axi_awburst(m_axi_awburst),.m_axi_awlock(m_axi_awlock),.m_axi_awcache(m_axi_awcache),.m_axi_awprot(m_axi_awprot),.m_axi_awvalid(m_axi_awvalid),.m_axi_awready(m_axi_awready),.m_axi_wdata(m_axi_wdata),.m_axi_wstrb(m_axi_wstrb),.m_axi_wlast(m_axi_wlast),.m_axi_wvalid(m_axi_wvalid),.m_axi_wready(m_axi_wready),.m_axi_bid(m_axi_bid),.m_axi_bresp(m_axi_bresp),.m_axi_bvalid(m_axi_bvalid),.m_axi_bready(m_axi_bready),.m_axi_arid(m_axi_arid),.m_axi_araddr(m_axi_araddr),.m_axi_arlen(m_axi_arlen),.m_axi_arsize(m_axi_arsize),.m_axi_arburst(m_axi_arburst),.m_axi_arlock(m_axi_arlock),.m_axi_arcache(m_axi_arcache),.m_axi_arprot(m_axi_arprot),.m_axi_arvalid(m_axi_arvalid),.m_axi_arready(m_axi_arready),.m_axi_rid(m_axi_rid),.m_axi_rdata(m_axi_rdata),.m_axi_rresp(m_axi_rresp),.m_axi_rlast(m_axi_rlast),.m_axi_rvalid(m_axi_rvalid),.m_axi_rready(m_axi_rready),.write_fault(write_fault),.perfBusy(perfBusy),.perfTriangleRendering(perfTriangleRendering),.perfRasterizerStall(perfRasterizerStall));
reg [63:0] staging[0:7],committed[0:7];
integer i,cycle=0,wbeat=0,readbeat=0,rxwords=0,delay_b=0,b_count=0;
reg writing=0,reading=0;
reg [5:0] write_id,read_id;
always @(negedge aclk) begin
 cycle=cycle+1;m_axi_awready=!writing&&!m_axi_bvalid;
 m_axi_wready=writing&&(cycle%3!=0);m_axi_arready=!reading;
 m_cmd_resp_axis_tready=(cycle%4!=0);
end
always @(posedge aclk) begin
 if(m_axi_awvalid&&m_axi_awready) begin
  if(m_axi_awaddr!=32'h10800000||m_axi_awsize!=3||m_axi_awlen!=7) $fatal(1,"Upload AW");
  writing<=1;wbeat<=0;write_id<=m_axi_awid;
 end
 if(m_axi_wvalid&&m_axi_wready) begin
  if(m_axi_wstrb!=8'hff||m_axi_wdata[31:0]!=(32'ha5a50000+wbeat*2)||m_axi_wdata[63:32]!=(32'ha5a50001+wbeat*2)) $fatal(1,"Upload bytes");
  if(m_axi_wlast!=(wbeat==7)) $fatal(1,"Upload WLAST");
  staging[wbeat]<=m_axi_wdata;wbeat<=wbeat+1;
  if(m_axi_wlast) begin writing<=0;delay_b<=80;end
 end
 if(delay_b>0) begin
  delay_b<=delay_b-1;
  if(delay_b==1) begin m_axi_bid<=write_id;m_axi_bvalid<=1;end
 end
 if(m_axi_bvalid&&m_axi_bready) begin
  m_axi_bvalid<=0;b_count<=b_count+1;
  for(i=0;i<8;i=i+1) committed[i]<=staging[i];
 end
 if(m_axi_arvalid&&m_axi_arready) begin
  if(b_count!=1) $fatal(1,"Resource LOAD passed pending STORE B response");
  if(m_axi_araddr!=32'h10800000||m_axi_arsize!=3||m_axi_arlen!=7) $fatal(1,"Upload AR");
  reading<=1;readbeat<=0;read_id<=m_axi_arid;
 end
 if(reading&&!m_axi_rvalid) begin
  m_axi_rvalid<=1;m_axi_rdata<=committed[readbeat];m_axi_rid<=read_id;m_axi_rlast<=readbeat==7;
 end
 if(m_axi_rvalid&&m_axi_rready) begin
  m_axi_rvalid<=0;readbeat<=readbeat+1;if(m_axi_rlast) reading<=0;
 end
 if(m_cmd_resp_axis_tvalid&&m_cmd_resp_axis_tready) begin
  if(m_cmd_resp_axis_tdata!=(32'ha5a50000+rxwords)||m_cmd_resp_axis_tlast!=(rxwords==15)) $fatal(1,"RX data/TLAST");
  rxwords<=rxwords+1;
 end
end
task command(input [31:0] word);
 begin
  @(negedge aclk);s_cmd_axis_tvalid=1;s_cmd_axis_tdata=word;
  do @(posedge aclk);while(!s_cmd_axis_tready);
  @(negedge aclk);s_cmd_axis_tvalid=0;
 end
endtask
initial begin
 for(i=0;i<8;i=i+1) committed[i]=0;
 repeat(10) @(negedge aclk);resetn=1;fb_swapped=1;
 command(32'hd0000040);command(32'h10800000);
 for(integer n=0;n<16;n=n+1) command(32'ha5a50000+n);
 command(32'h70000040);command(32'h10800000);
 wait(rxwords==16);#1;
 if(write_fault||swap_fb) $fatal(1,"Upload fault/unexpected swap");
 $display("PASS GPU upload: STORE/LOAD at texture pool, 64-bit AXI, 32-bit RX, delayed B fence, stalls and TLAST");$finish;
end
initial begin #1000000;$fatal(1,"Upload watchdog");end
endmodule
