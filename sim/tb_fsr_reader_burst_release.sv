`timescale 1ns/1ps
module tb_fsr_reader_burst_release;
 reg clk=0;always #2.5 clk=~clk;
 reg rst=1,start=0,abort=0,ready=0,allow_ar=1;
 reg [31:0] frame_base=32'h20000000;
 reg [19:0] frame_pixels=96000;
 wire idle,done,aborted,error,valid,arvalid,rready;
 wire [127:0] data;
 wire [31:0] araddr;wire [7:0] arlen;wire [2:0] arsize;wire [1:0] arburst;
 reg bus_active=0;reg [31:0] bus_base=0;
 integer beat=0,length=0,cycle=0,finished=0,consumed=0,inject=0;
 reg done_seen=0,aborted_seen=0,error_seen=0,check_pixels=1;
 wire arready=allow_ar&&!bus_active;
 wire rvalid=bus_active&&(cycle%11!=7);
 wire rlast=inject==2 ? beat==7 : inject==3 ? beat==length : beat==length-1;
 wire [1:0] rresp=(inject==1&&beat==17)?2'b10:2'b00;
 function automatic [127:0] pattern(input [31:0] address);
  pattern={address^32'hc39a1203,address^32'h742ab091,address^32'h12345678,address^32'hf0d3ba21};
 endfunction
 wire [127:0] rdata=pattern(bus_base+beat*16);
 rix_frame_reader_dynamic dut(.clk(clk),.rst(rst),.start(start),.abort(abort),
  .frame_base(frame_base),.frame_pixels(frame_pixels),.idle(idle),.done(done),.aborted(aborted),.error(error),
  .data(data),.valid(valid),.ready(ready),.m_axi_araddr(araddr),.m_axi_arlen(arlen),.m_axi_arsize(arsize),
  .m_axi_arburst(arburst),.m_axi_arvalid(arvalid),.m_axi_arready(arready),.m_axi_rdata(rdata),
  .m_axi_rresp(rresp),.m_axi_rlast(rlast),.m_axi_rvalid(rvalid),.m_axi_rready(rready));
 always @(posedge clk) begin
  if(rst) begin bus_active<=0;beat<=0;length<=0;cycle<=0;finished<=0;consumed<=0;
   done_seen<=0;aborted_seen<=0;error_seen<=0;end
  else begin
   cycle<=cycle+1;
   if(done)done_seen<=1;if(aborted)aborted_seen<=1;if(error)error_seen<=1;
   if(arvalid&&arready)begin
    if(bus_active||arsize!=4||arburst!=1||araddr[3:0]!=0||araddr[11:0]+(integer'(arlen)+1)*16>4096)
     $fatal(1,"BAD_AXI_READ_REQUEST");
    bus_active<=1;bus_base<=araddr;length<=integer'(arlen)+1;beat<=0;
   end
   if(rvalid&&rready)begin
    if(rlast)begin bus_active<=0;finished<=finished+1;end else beat<=beat+1;
   end
   if(valid&&ready)begin
    if(check_pixels&&data!==pattern(frame_base+consumed*16))
     $fatal(1,"BUFFERED_PIXEL_MISMATCH at beat %d",consumed);
    consumed<=consumed+1;
   end
  end
 end
 task automatic reset_case(input integer pixels,input integer fault);
  @(negedge clk);rst=1;start=0;abort=0;ready=0;allow_ar=1;inject=fault;check_pixels=1;
  frame_pixels=pixels;repeat(5)@(negedge clk);rst=0;
 endtask
 task automatic begin_frame;
  @(negedge clk);start=1;@(negedge clk);start=0;
 endtask
 task automatic full_frame(input integer pixels);
  integer t;
  reset_case(pixels,0);begin_frame();
  for(t=0;t<800&&finished==0;t=t+1)@(negedge clk);
  if(finished!=1||bus_active||consumed!=0)
   $fatal(1,"READ_BURST_HELD_BY_DOWNSTREAM_READY pixels=%d",pixels);
  repeat(12)begin @(negedge clk);if(arvalid||bus_active||consumed!=0)$fatal(1,"NEXT_BURST_BEFORE_CACHE_DRAIN");end
  for(t=0;t<1000000&&!done_seen;t=t+1)begin @(negedge clk);ready=(t%13!=3)&&(t%13!=4);end
  @(negedge clk);ready=0;
  if(!done_seen||error_seen||aborted_seen||!idle||bus_active||consumed!=pixels/4)
   $fatal(1,"FULL_BUFFERED_FRAME_FAILED pixels=%d beats=%d",pixels,consumed);
  $display("PASS BURST_RELEASE_FULL pixels=%d beats=%d",pixels,consumed);
 endtask
 task automatic finish_cancel(input integer expected_error);
  integer t;
  for(t=0;t<3000&&!idle;t=t+1)@(negedge clk);
  repeat(3)@(negedge clk);
  if(!idle||bus_active||!aborted_seen||done_seen||consumed!=0||error_seen!=expected_error)
   $fatal(1,"CANCEL_OR_FAULT_DID_NOT_DRAIN error=%d expected=%d",error_seen,expected_error);
 endtask
 integer t,f;
 initial begin
  full_frame(96000);full_frame(384000);full_frame(15360);
  reset_case(384000,0);allow_ar=0;begin_frame();
  for(t=0;t<100&&!arvalid;t=t+1)@(negedge clk);
  if(!arvalid)$fatal(1,"NO_ISSUE_TO_CANCEL");abort=1;
  repeat(8)begin @(negedge clk);if(!arvalid||araddr!=frame_base)$fatal(1,"WITHDREW_CANCELLED_ARVALID");end
  allow_ar=1;finish_cancel(0);$display("PASS BURST_CANCEL_ISSUE");
  reset_case(384000,0);begin_frame();
  for(t=0;t<200&&beat<16;t=t+1)@(negedge clk);
  if(!bus_active||beat<16)$fatal(1,"NO_READ_TO_CANCEL");abort=1;
  finish_cancel(0);$display("PASS BURST_CANCEL_READ");
  reset_case(384000,0);begin_frame();
  for(t=0;t<800&&!valid;t=t+1)@(negedge clk);
  if(!valid||bus_active||finished!=1)$fatal(1,"NO_STREAM_TO_CANCEL");abort=1;
  finish_cancel(0);$display("PASS BURST_CANCEL_STREAM");
  for(f=1;f<=3;f=f+1)begin
   reset_case(384000,f);begin_frame();
   // Wait until an actual request is accepted, then require its whole response
   // (including malformed late RLAST) to drain without publishing any pixels.
   for(t=0;t<100&&!bus_active;t=t+1)@(negedge clk);
   if(!bus_active)$fatal(1,"NO_FAULT_TRANSACTION");
   finish_cancel(1);$display("PASS BURST_FAULT_DRAIN kind=%d",f);
  end
  $display("PASS FSR_READER_BURST_RELEASE 9 cases");$finish;
 end
 initial begin #20000000;$fatal(1,"BURST_RELEASE_TEST_TIMEOUT");end
endmodule
