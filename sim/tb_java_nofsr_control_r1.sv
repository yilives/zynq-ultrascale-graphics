`timescale 1ns/1ps
module tb_java_nofsr_control_r1;
 reg clk=0,rst=1;always #5 clk=~clk;
 reg [31:0] live_status=0;reg [383:0] live_counters=0;wire enable;
 wire [31:0] post_control;reg [31:0] post_active=0,last_fb_addr=0;
 wire capture_req;wire [12:0] capture_addr;reg capture_ack=0;reg [15:0] capture_data=16'h1234;
 wire snapshot_request,snapshot_release;wire [31:0] snapshot_command_token;
 wire [31:0] snapshot_status,snapshot_token,snapshot_frame_id,snapshot_expired_count;
 reg snapshot_start=0,snapshot_done=0;wire snapshot_pending;
 rix_frame_snapshot #(.LEASE_CYCLES(5000)) lease(.clk(clk),.rst(rst),.request(snapshot_request),
  .release_snapshot(snapshot_release),.command_token(snapshot_command_token),.capture_start(snapshot_start),
  .capture_done(snapshot_done),.capture_error(live_status[2]),.capture_frame_id(32'd456),.pending(snapshot_pending),
  .status(snapshot_status),.token(snapshot_token),.frame_id(snapshot_frame_id),.expired_count(snapshot_expired_count));
 reg [7:0] s_axi_awaddr=0,s_axi_araddr=0;
 reg s_axi_awvalid=0,s_axi_wvalid=0,s_axi_bready=0,s_axi_arvalid=0,s_axi_rready=0;
 wire s_axi_awready,s_axi_wready,s_axi_bvalid,s_axi_arready,s_axi_rvalid;
 reg [31:0] s_axi_wdata=0;reg [3:0] s_axi_wstrb=0;
 wire [31:0] s_axi_rdata;wire [1:0] s_axi_bresp,s_axi_rresp;
 rix_control #(.CONFIG_HASH(32'h12345678),.PS_GFX_BASE(32'h10000000)) dut(.*);
 task wr(input [7:0] addr,input [31:0] data,input [3:0] strb,input reverse,input [1:0] response);
  begin
   fork
    begin
     repeat(reverse?5:1) @(negedge clk);s_axi_awaddr=addr;s_axi_awvalid=1;
     do @(posedge clk);while(!s_axi_awready);
     @(negedge clk);s_axi_awvalid=0;
    end
    begin
     repeat(reverse?1:5) @(negedge clk);s_axi_wdata=data;s_axi_wstrb=strb;s_axi_wvalid=1;
     do @(posedge clk);while(!s_axi_wready);
     @(negedge clk);s_axi_wvalid=0;
    end
   join
   wait(s_axi_bvalid);
   repeat(5) begin @(negedge clk);if(!s_axi_bvalid||s_axi_bresp!=response) $fatal(1,"B unstable/incorrect");end
   s_axi_bready=1;@(negedge clk);s_axi_bready=0;
  end
 endtask
 task rd(input [7:0] addr,input [31:0] expected);
  begin
   @(negedge clk);s_axi_araddr=addr;s_axi_arvalid=1;
   do @(posedge clk);while(!s_axi_arready);
   @(negedge clk);s_axi_arvalid=0;wait(s_axi_rvalid);
   repeat(5) begin @(negedge clk);if(!s_axi_rvalid||s_axi_rresp||s_axi_rdata!==expected) $fatal(1,"R unstable/incorrect addr=%h value=%h expected=%h",addr,s_axi_rdata,expected);end
   s_axi_rready=1;@(negedge clk);s_axi_rready=0;
  end
 endtask
 integer i;
 initial begin
  repeat(5) @(negedge clk);rst=0;
  // Registers remain readable before MIG/calibration readiness.
  rd(0,32'h52495801);rd(12,32'h12345678);rd(8,0);rd(8'h44,32'h10000000);rd(8'h48,32'h02000000);
  wr(4,1,15,0,2);if(enable) $fatal(1,"Enabled before readiness");
  live_status=3;wr(4,1,15,1,0);rd(4,1);
  wr(4,0,0,0,0);if(!enable) $fatal(1,"WSTRB ignored");
  for(i=0;i<12;i=i+1) live_counters[i*32+:32]=100+i;
  wr(8'h40,1,15,0,0);live_counters=0;
  for(i=0;i<12;i=i+1) rd(8'h10+i*4,100+i);
  wr(8'h40,1,0,1,0);rd(8'h10,100);
  wr(8'hff,1,15,1,2);
  rd(8'h50,32'h50535431);wr(8'h54,32'h321,15,0,0);rd(8'h54,32'h321);
  wr(8'h54,3,15,1,0);rd(8'h54,3);wr(8'h54,32'h400,15,0,2);rd(8'h54,3);
  wr(8'h64,1,15,0,0);rd(8'h64,1);wr(8'h64,1,15,1,2);
  capture_ack=1;rd(8'h68,1);wr(8'h6c,5999,15,0,0);rd(8'h6c,5999);rd(8'h70,32'h1234);
  rd(8'h74,32'h534e5031);rd(8'h88,32'ha1400000);rd(8'h90,384000);rd(8'h94,2000);
  rd(8'hb0,32'h4a324e31);rd(8'hb4,2);rd(8'hb8,0);rd(8'hbc,0);
  wr(8'h78,0,15,0,2);wr(8'h78,123,3,1,2);wr(8'h78,123,15,1,0);
  rd(8'h7c,1);rd(8'h80,123);wr(8'h78,124,15,0,2);wr(8'h80,124,15,1,2);
  @(negedge clk);snapshot_start=1;@(negedge clk);snapshot_start=0;rd(8'h7c,2);
  @(negedge clk);snapshot_done=1;@(negedge clk);snapshot_done=0;rd(8'h7c,3);rd(8'h84,456);
  wr(8'h80,123,15,0,0);rd(8'h7c,0);wr(8'h80,123,15,1,2);wr(8'h78,123,15,1,2);
  wr(8'h78,124,15,0,0);wr(8'h80,124,15,1,0);rd(8'h7c,0);
  live_status=7;repeat(3) @(negedge clk);rd(4,0);wr(4,1,15,0,2);
  $display("PASS JAVA_NOFSR_CONTROL: AW/W reorder, B/R backpressure, WSTRB, leased snapshot token/busy/stale rejection, pre-ready status and fault gating");$finish;
 end
 initial begin #100000;$fatal(1,"Control watchdog");end
endmodule
