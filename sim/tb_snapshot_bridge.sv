`timescale 1ns/1ps
// The AXI RAM mutates the PS frame every swap. A CPU lease must retain the
// exact expanded pixels even while later frames keep being presented.
module tb_snapshot_bridge;
 reg clk=0,rst=1;always #5 clk=~clk;
 reg swap_fb=0,front_slot=0;wire fb_swapped,present_valid,present_slot,copy_done,fault;
 wire [31:0] frame_id,swap_count,copy_count,present_count,read_errors,write_errors,timeouts,completed_source_base;
 wire [7:0] first_error;
 reg request=0,release_snapshot=0;reg [31:0] command_token=0;
 wire snapshot_pending,snapshot_start,snapshot_done,snapshot_error;
 wire [31:0] status,token,leased_frame,expired_count;
 reg freeze=0,fail_snapshot_b=0;
 wire [31:0] m_ps_araddr,m_pl_awaddr;wire [7:0] m_ps_arlen,m_pl_awlen;
 wire [2:0] m_ps_arsize,m_pl_awsize;wire [1:0] m_ps_arburst,m_pl_awburst;
 wire m_ps_arvalid,m_ps_rready,m_pl_awvalid,m_pl_wvalid,m_pl_wlast,m_pl_bready;
 wire [127:0] m_pl_wdata;wire [15:0] m_pl_wstrb;
 reg m_ps_arready=0,m_ps_rvalid=0,m_pl_awready=0,m_pl_wready=0,m_pl_bvalid=0;
 reg [63:0] m_ps_rdata=0;reg [1:0] m_pl_bresp=0;
 integer cycles=0,rdelay=0,bdelay=0,snapshot_writes=0,ps_generation=1;
 reg have_aw=0,have_w=0;reg [31:0] held_address;reg [127:0] held_data;
 reg [127:0] snapshot_ram[0:1],raw_ram[0:3],saved[0:1];
 rix_frame_snapshot #(.LEASE_CYCLES(5000)) lease(.clk(clk),.rst(rst),.request(request),
  .release_snapshot(release_snapshot),.command_token(command_token),.capture_start(snapshot_start),
  .capture_done(snapshot_done),.capture_error(fault),.capture_frame_id(frame_id+1),.pending(snapshot_pending),
  .status(status),.token(token),.frame_id(leased_frame),.expired_count(expired_count));
 rix_frame_bridge #(.WIDTH(4),.HEIGHT(2),.PS_GFX_BASE(32'h60000000),.TIMEOUT_CYCLES(20000),.BURST_BEATS(1)) dut(
  .clk(clk),.rst(rst),.enable(1'b1),.mig_ready(1'b1),.lcd_running(1'b1),.swap_fb(swap_fb),
  .fb_addr(32'h60000000),.fb_size(20'd8),.fb_swapped(fb_swapped),.front_slot(front_slot),
  .present_valid(present_valid),.present_slot(present_slot),.frame_id(frame_id),
  .present_ack(present_valid),.presented_id(frame_id),.copy_done(copy_done),.fault(fault),
  .completed_source_base(completed_source_base),.snapshot_pending(snapshot_pending),.snapshot_start(snapshot_start),
  .snapshot_done(snapshot_done),.snapshot_error(snapshot_error),.first_error(first_error),.swap_count(swap_count),
  .copy_count(copy_count),.present_count(present_count),.read_errors(read_errors),.write_errors(write_errors),.timeouts(timeouts),
  .m_ps_araddr(m_ps_araddr),.m_ps_arlen(m_ps_arlen),.m_ps_arsize(m_ps_arsize),.m_ps_arburst(m_ps_arburst),
  .m_ps_arvalid(m_ps_arvalid),.m_ps_arready(m_ps_arready),.m_ps_rdata(m_ps_rdata),.m_ps_rresp(2'b0),
  .m_ps_rlast(1'b1),.m_ps_rvalid(m_ps_rvalid),.m_ps_rready(m_ps_rready),
  .m_pl_awaddr(m_pl_awaddr),.m_pl_awlen(m_pl_awlen),.m_pl_awsize(m_pl_awsize),.m_pl_awburst(m_pl_awburst),
  .m_pl_awvalid(m_pl_awvalid),.m_pl_awready(m_pl_awready),.m_pl_wdata(m_pl_wdata),.m_pl_wstrb(m_pl_wstrb),
  .m_pl_wlast(m_pl_wlast),.m_pl_wvalid(m_pl_wvalid),.m_pl_wready(m_pl_wready),
  .m_pl_bresp(m_pl_bresp),.m_pl_bvalid(m_pl_bvalid),.m_pl_bready(m_pl_bready));
 function [15:0] pixel(input integer generation,index);
  pixel=16'(generation*997+index*333);
 endfunction
 function [31:0] expand(input [15:0] p);
  expand={8'b0,p[15:11],p[15:13],p[10:5],p[10:9],p[4:0],p[4:2]};
 endfunction
 function [127:0] expected(input integer generation,word_index);
  for(integer k=0;k<4;k++)expected[k*32+:32]=expand(pixel(generation,word_index*4+k));
 endfunction
 always @(negedge clk) begin
  cycles=cycles+1;
  m_ps_arready=!freeze&&cycles%3!=0;
  m_pl_awready=!freeze&&cycles%4==0;
  m_pl_wready=!freeze&&cycles%5!=0;
 end
 always @(posedge clk) begin
  if(rst)begin rdelay<=0;bdelay<=0;m_ps_rvalid<=0;m_pl_bvalid<=0;have_aw<=0;have_w<=0;snapshot_writes<=0;end
  else begin
   if(m_ps_arvalid&&m_ps_arready)begin
    for(integer k=0;k<4;k++)m_ps_rdata[k*16+:16]<=pixel(ps_generation,((m_ps_araddr-32'h60000000)/8)*4+k);
    rdelay<=3;
   end
   if(rdelay>0)begin rdelay<=rdelay-1;if(rdelay==1)m_ps_rvalid<=1;end
   if(m_ps_rvalid&&m_ps_rready)m_ps_rvalid<=0;
   if(m_pl_awvalid&&m_pl_awready)begin held_address<=m_pl_awaddr;have_aw<=1;end
   if(m_pl_wvalid&&m_pl_wready)begin held_data<=m_pl_wdata;have_w<=1;end
   if(have_aw&&have_w&&!bdelay&&!m_pl_bvalid)begin
    bdelay<=17;have_aw<=0;have_w<=0;
    m_pl_bresp<=(fail_snapshot_b&&held_address>=32'h21400000)?2:0;
   end
   if(bdelay>0)begin bdelay<=bdelay-1;if(bdelay==1)m_pl_bvalid<=1;end
   if(m_pl_bvalid&&m_pl_bready)begin
    m_pl_bvalid<=0;
    if(held_address>=32'h21400000)begin
     if(status[1:0]!=2)$fatal(1,"snapshot write outside COPYING lease");
     if(held_address>32'h21400010)$fatal(1,"snapshot address outside frame");
     snapshot_ram[(held_address-32'h21400000)/16]<=held_data;snapshot_writes<=snapshot_writes+1;
    end else raw_ram[(held_address>=32'h100000 ? 2:0)+((held_address&32'hfffff)/16)]<=held_data;
   end
   if(status[1:0]==3&&(snapshot_writes%2!=0||m_pl_bvalid&&held_address>=32'h21400000))$fatal(1,"READY before final B response");
  end
 end
 task command(input bit releasing,input integer value);
  @(negedge clk);command_token=value;request=!releasing;release_snapshot=releasing;
  @(negedge clk);request=0;release_snapshot=0;
 endtask
 task frame(input integer generation);
  @(negedge clk);ps_generation=generation;swap_fb=1;
  wait(fb_swapped);@(negedge clk);front_slot=present_slot;swap_fb=0;
  repeat(4)@(negedge clk);
 endtask
 task reset_test;
  @(negedge clk);rst=1;swap_fb=0;request=0;release_snapshot=0;freeze=0;fail_snapshot_b=0;
  repeat(5)@(negedge clk);rst=0;repeat(3)@(negedge clk);
 endtask
 integer i,old_count;
 initial begin
  reset_test();
  command(0,11);frame(1);
  if(status!=3||token!=11||leased_frame!=1||snapshot_writes!=2)$fatal(1,"lease metadata");
  for(i=0;i<2;i++)begin
   if(snapshot_ram[i]!==expected(1,i)||snapshot_ram[i]!==raw_ram[(front_slot?2:0)+i])$fatal(1,"snapshot != exact presented pixels");
   saved[i]=snapshot_ram[i];
  end
  // CPU keeps its lease while the game advances through many different PS frames.
  for(i=2;i<=25;i++)begin
   frame(i);
   if(status!=3||snapshot_ram[0]!==saved[0]||snapshot_ram[1]!==saved[1]||snapshot_writes!=2)$fatal(1,"CPU lease overwritten by renderer");
  end
  if(present_count!=25)$fatal(1,"game blocked by CPU lease");
  command(1,10);if(status!=3)$fatal(1,"stale release stole lease");
  command(1,11);if(status[1:0]!=0)$fatal(1,"release failed");
  command(0,12);frame(26);
  if(status!=3||leased_frame!=26||snapshot_ram[0]!==expected(26,0))$fatal(1,"reacquisition captured wrong frame");
  // An abandoned READY lease expires; the game remains usable.
  wait(status[1:0]==0);if(expired_count!=1)$fatal(1,"READY watchdog");frame(27);
  command(0,13);command(1,13);frame(28);if(snapshot_writes!=4)$fatal(1,"canceled pending capture wrote memory");
  // Abort/expiry during a stalled accepted copy must not withdraw AXI VALID.
  command(0,14);
  @(negedge clk);ps_generation=29;swap_fb=1;
  wait(m_pl_awvalid&&m_pl_awaddr==32'h21400000);freeze=1;@(negedge clk);
  command(1,14);repeat(12)@(negedge clk);
  if(status[1:0]!=2||!status[8]||!m_pl_awvalid)$fatal(1,"cancel withdrew in-flight AXI or released too early");
  freeze=0;wait(fb_swapped);@(negedge clk);swap_fb=0;repeat(4)@(negedge clk);
  if(status[1:0]!=0||fault)$fatal(1,"canceled copy did not drain");
  command(0,15);@(negedge clk);ps_generation=30;swap_fb=1;
  wait(m_pl_awvalid&&m_pl_awaddr==32'h21400000);freeze=1;@(negedge clk);
  repeat(5100)@(negedge clk);
  if(status[1:0]!=2||!status[8]||!m_pl_awvalid||expired_count!=2)$fatal(1,"COPYING watchdog/drain");
  freeze=0;wait(fb_swapped);@(negedge clk);swap_fb=0;repeat(4)@(negedge clk);
  if(status[1:0]!=0||fault)$fatal(1,"expired copy did not drain");
  command(0,16);wait(status[1:0]==0);if(expired_count!=3)$fatal(1,"PENDING watchdog");
  command(0,17);frame(31);if(status!=3)$fatal(1,"recovery after abandoned requests");
  reset_test();command(0,18);fail_snapshot_b=1;swap_fb=1;wait(fault);repeat(5)@(negedge clk);
  if(status[1:0]!=0||copy_count||present_count||write_errors!=1)$fatal(1,"failed snapshot published READY/presented");
  reset_test();if(status||token||expired_count)$fatal(1,"reset retained ownership");
  $display("PASS snapshot: exact raw pixels, immutable across 25 game frames, token release/reacquire, pending/copy/ready watchdogs, cancel drains stalled AXI, B error and reset");$finish;
 end
 initial begin #2000000;$fatal(1,"snapshot test watchdog");end
endmodule
