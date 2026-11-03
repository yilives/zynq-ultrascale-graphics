`timescale 1ns/1ps
module tb_gpu_exact;
reg [31:0] exact_commands[0:2];
initial $readmemh("framebuffer_sizes.mem",exact_commands);
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
integer cycle=0,beat=0,beattotal=0,delay_b=0,aw_count=0,b_count=0;
reg active=0;
reg [5:0] saved_id;
reg [31:0] saved_addr;
always @(negedge aclk) begin
 cycle=cycle+1;
 m_axi_awready=!active&&!m_axi_bvalid&&!delay_b;
 m_axi_wready=active&&(cycle%3!=0);
end
always @(posedge aclk) begin
 if(m_axi_awvalid&&m_axi_awready) begin
  if(m_axi_awaddr!=32'h10000000+aw_count*128||aw_count>=500||m_axi_awsize!=3||m_axi_awlen!=15) $fatal(1,"GPU AW incorrect addr=%h size=%h len=%h",m_axi_awaddr,m_axi_awsize,m_axi_awlen);
  active<=1;saved_id<=m_axi_awid;saved_addr<=m_axi_awaddr;
  beat<=0;beattotal<=m_axi_awlen+1;aw_count<=aw_count+1;
 end
 if(m_axi_wvalid&&m_axi_wready) begin
  if(m_axi_wdata!==64'hf800f800f800f800||m_axi_wstrb!=8'hff) begin
   $display("config clear=%h mask=%h size=%h",gpu.rixif.colorBufferClearColor,gpu.rixif.colorBufferMask,gpu.rixif.colorBufferSize);
   $fatal(1,"GPU clear color/layout %h strb=%h",m_axi_wdata,m_axi_wstrb);
  end
  if(m_axi_wlast!=(beat==beattotal-1)) $fatal(1,"GPU WLAST");
  beat<=beat+1;
  if(m_axi_wlast) begin active<=0;delay_b<=80;end
 end
 if(delay_b>0) begin
  if(swap_fb) $fatal(1,"GPU swap before final DDR write response");
  delay_b<=delay_b-1;
  if(delay_b==1) begin m_axi_bvalid<=1;m_axi_bid<=saved_id;m_axi_bresp<=$test$plusargs("fail_bresp")?2:0;end
 end
 if(m_axi_bvalid&&m_axi_bready) begin m_axi_bvalid<=0;b_count<=b_count+1;end
end
task command(input [31:0] word);
 begin
  @(negedge aclk);s_cmd_axis_tvalid=1;s_cmd_axis_tdata=word;
  do @(posedge aclk); while(!s_cmd_axis_tready);
  $display("CMD accepted %h at %t",word,$time);
  @(negedge aclk);s_cmd_axis_tvalid=0;
 end
endtask
initial begin
 repeat(10) @(negedge aclk);resetn=1;fb_swapped=1;m_cmd_resp_axis_tready=1;
 fork
 begin
 command(32'h90000040);command(0); // DDU ST0 -> ST1, 64-byte payload
 command(32'h10000000);command(0); // disable scissor and optional fragment features
 command(32'h10000009);command(32'h00500190); // 8x8, minimum full 128-byte AXI burst
 command(32'h10000010);command(32'h10000000); // color base
 command(32'h10000003);command(32'h00078000); // enable RGBA writes (bits 15..18)
 command(32'h10000001);command(32'hff0000ff); // RRGGBBAA red clear color
 command(exact_commands[0]); // clear 64 pixels
 command(exact_commands[1]); // commit 64 pixels (must wait for B)
 command(exact_commands[2]); // swap 64 pixels with vsync
 command(0);command(0);command(0); // padded DDU payload
 end
 begin
 if($test$plusargs("fail_bresp")) begin
  wait(write_fault);#1;
  if(swap_fb||b_count!=1) $fatal(1,"GPU write error published");
  repeat(20) @(negedge aclk);if(swap_fb) $fatal(1,"GPU fault bypassed");
  $display("PASS GPU IF: non-OK DDR B response latches fault and blocks swap");
 end else begin
  wait(swap_fb);#1;
  if(fb_addr!=32'h10000000||fb_size!=96000||aw_count!=500||b_count!=500||write_fault) $fatal(1,"GPU swap metadata/fence");
  $display("PASS GPU exact framebuffer: real C++ commands, 32000 pixels in exactly 64000 bytes, 96000-pixel swap, delayed B fence");
 end
 $finish;
 end
 join
end
initial begin #10000000;$display("aw=%d b=%d fault=%b swap=%b drained=%b awvalid=%b wvalid=%b idle=%b",aw_count,b_count,write_fault,swap_fb,gpu.writes_drained,gpu.xbar_axi_awvalid,gpu.xbar_axi_wvalid,gpu.framebuffer_path_idle);$fatal(1,"GPU watchdog");end
endmodule
