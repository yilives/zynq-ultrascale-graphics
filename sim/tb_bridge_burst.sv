`timescale 1ns/1ps
module bridge_burst_case #(
 parameter BURST=16,W=400,H=240,STRESS=0
)(output reg finished=0,output integer measured_cycles=0);
 localparam WORDS=W*H/4;
 reg clk=0,rst=1;always #5 clk=~clk;
 reg swap_fb=0,front_slot=0,auto_ack=1;
 reg [31:0] fb_addr=32'h60000000;
 reg [19:0] fb_size=W*H;
 wire fb_swapped,present_valid,present_slot,copy_done,fault;
 wire [31:0] frame_id,swap_count,copy_count,present_count,read_errors,write_errors,timeouts,completed_source_base;
 wire [7:0] first_error;
 reg request=0,release_snapshot=0;reg [31:0] command_token=0;
 wire snapshot_pending,snapshot_start,snapshot_done,snapshot_error;
 wire [31:0] status,token,leased_frame,expired_count;
 wire [31:0] m_ps_araddr,m_pl_awaddr;
 wire [7:0] m_ps_arlen,m_pl_awlen;
 wire [2:0] m_ps_arsize,m_pl_awsize;
 wire [1:0] m_ps_arburst,m_pl_awburst;
 wire m_ps_arvalid,m_ps_rready,m_pl_awvalid,m_pl_wvalid,m_pl_wlast,m_pl_bready;
 wire [127:0] m_pl_wdata;wire [15:0] m_pl_wstrb;
 reg m_ps_arready=0,m_ps_rvalid=0,m_ps_rlast=0,m_pl_awready=0,m_pl_wready=0,m_pl_bvalid=0;
 reg [63:0] m_ps_rdata=0;reg [1:0] m_ps_rresp=0,m_pl_bresp=0;
 integer cycle=0,generation=1,ar_count=0,aw_count=0,r_count=0,w_count=0,b_count=0;
 integer read_left=0,read_position=0,read_word=0,read_generation=0,read_delay=0;
 integer aw_words=0,w_words=0,bdelay=0,inject_read=0,inject_b=0,malformed=0;
 reg have_aw=0,write_last_seen=0,stall_read=0,stall_write=0;
 reg [31:0] held_aw=0,expected_source=32'h60000000;
 reg [63:0] seen[0:WORDS-1];
 reg [127:0] raw_ram[0:2*WORDS-1],snapshot_ram[0:WORDS-1],held_w[0:15],saved[0:WORDS-1];
 reg old_ar_stall=0,old_aw_stall=0,old_w_stall=0;
 reg [39:0] old_ar,old_aw;
 reg [144:0] old_w;
 rix_frame_snapshot #(.LEASE_CYCLES(200000000)) lease(.clk(clk),.rst(rst),.request(request),
  .release_snapshot(release_snapshot),.command_token(command_token),.capture_start(snapshot_start),
  .capture_done(snapshot_done),.capture_error(fault),.capture_frame_id(frame_id+1),.pending(snapshot_pending),
  .status(status),.token(token),.frame_id(leased_frame),.expired_count(expired_count));
 rix_frame_bridge #(.WIDTH(W),.HEIGHT(H),.PS_GFX_BASE(32'h60000000),.BURST_BEATS(BURST),
  .TIMEOUT_CYCLES(STRESS?400:100000000)) dut(
  .clk(clk),.rst(rst),.enable(1'b1),.mig_ready(1'b1),.lcd_running(1'b1),.swap_fb(swap_fb),.fb_addr(fb_addr),.fb_size(fb_size),
  .fb_swapped(fb_swapped),.front_slot(front_slot),.present_valid(present_valid),.present_slot(present_slot),.frame_id(frame_id),
  .present_ack(present_valid&&auto_ack),.presented_id(frame_id),.copy_done(copy_done),.fault(fault),
  .completed_source_base(completed_source_base),.snapshot_pending(snapshot_pending),.snapshot_start(snapshot_start),
  .snapshot_done(snapshot_done),.snapshot_error(snapshot_error),.first_error(first_error),.swap_count(swap_count),
  .copy_count(copy_count),.present_count(present_count),.read_errors(read_errors),.write_errors(write_errors),.timeouts(timeouts),
  .m_ps_araddr(m_ps_araddr),.m_ps_arlen(m_ps_arlen),.m_ps_arsize(m_ps_arsize),.m_ps_arburst(m_ps_arburst),
  .m_ps_arvalid(m_ps_arvalid),.m_ps_arready(m_ps_arready),.m_ps_rdata(m_ps_rdata),.m_ps_rresp(m_ps_rresp),
  .m_ps_rlast(m_ps_rlast),.m_ps_rvalid(m_ps_rvalid),.m_ps_rready(m_ps_rready),
  .m_pl_awaddr(m_pl_awaddr),.m_pl_awlen(m_pl_awlen),.m_pl_awsize(m_pl_awsize),.m_pl_awburst(m_pl_awburst),
  .m_pl_awvalid(m_pl_awvalid),.m_pl_awready(m_pl_awready),.m_pl_wdata(m_pl_wdata),.m_pl_wstrb(m_pl_wstrb),
  .m_pl_wlast(m_pl_wlast),.m_pl_wvalid(m_pl_wvalid),.m_pl_wready(m_pl_wready),
  .m_pl_bresp(m_pl_bresp),.m_pl_bvalid(m_pl_bvalid),.m_pl_bready(m_pl_bready));
 function [63:0] pixels(input integer gen,word_index);
  for(integer k=0;k<4;k++)pixels[k*16+:16]=16'(gen*997+word_index*4*333+k*333);
 endfunction
 function [127:0] expand(input [63:0] packed_pixels);
  reg [15:0] p;
  for(integer k=0;k<4;k++)begin
   p=packed_pixels[k*16+:16];expand[k*32+:32]={8'b0,p[15:11],p[15:13],p[10:5],p[10:9],p[4:0],p[4:2]};
  end
 endfunction
 always @(negedge clk)begin
  cycle=cycle+1;
  m_ps_arready=cycle%3!=0;
  // W can finish before AW is accepted, including for a 16-beat burst.
  m_pl_awready=!stall_write&&cycle%5==0&&w_words>0;
  m_pl_wready=!stall_write&&cycle%7!=0;
 end
 always @(posedge clk)begin:memory_model
  integer count,index,slot;
  if(rst)begin
   ar_count=0;aw_count=0;r_count=0;w_count=0;b_count=0;
   read_left=0;read_position=0;read_delay=0;have_aw=0;w_words=0;aw_words=0;
   bdelay=0;write_last_seen=0;m_ps_rvalid<=0;m_pl_bvalid<=0;
   old_ar_stall=0;old_aw_stall=0;old_w_stall=0;
  end else begin
   if(old_ar_stall&&(!m_ps_arvalid||{m_ps_araddr,m_ps_arlen}!==old_ar))$fatal(1,"AR changed under backpressure");
   if(old_aw_stall&&(!m_pl_awvalid||{m_pl_awaddr,m_pl_awlen}!==old_aw))$fatal(1,"AW changed under backpressure");
   if(old_w_stall&&(!m_pl_wvalid||{m_pl_wdata,m_pl_wstrb,m_pl_wlast}!==old_w))$fatal(1,"W changed under backpressure");
   old_ar_stall=m_ps_arvalid&&!m_ps_arready;old_ar={m_ps_araddr,m_ps_arlen};
   old_aw_stall=m_pl_awvalid&&!m_pl_awready;old_aw={m_pl_awaddr,m_pl_awlen};
   old_w_stall=m_pl_wvalid&&!m_pl_wready;old_w={m_pl_wdata,m_pl_wstrb,m_pl_wlast};
   if(m_ps_arvalid&&m_ps_arready)begin
    count=m_ps_arlen+1;
    if(read_left||m_ps_rvalid||m_ps_araddr[2:0]||count>BURST||m_ps_arsize!=3||m_ps_arburst!=1||
       m_ps_araddr[11:0]+count*8>4096)$fatal(1,"PS burst layout/overlap");
    read_word=(m_ps_araddr-expected_source)/8;
    if(read_word<0||read_word+count>WORDS||count!=(WORDS-read_word<BURST?WORDS-read_word:BURST))$fatal(1,"PS burst coverage/tail");
    read_generation=generation;read_position=0;read_left=malformed==1?count/2:malformed==2?count+1:count;
    read_delay=8;ar_count=ar_count+1;
   end
   if(m_ps_rvalid&&m_ps_rready)begin
    if(read_word+read_position<WORDS)seen[read_word+read_position]=m_ps_rdata;
    read_position=read_position+1;read_left=read_left-1;r_count=r_count+1;m_ps_rvalid<=0;
   end
   if(read_delay>0)read_delay=read_delay-1;
   else if(read_left&&!m_ps_rvalid&&!stall_read&&cycle%4!=0)begin
    m_ps_rdata<=pixels(read_generation,read_word+read_position);
    m_ps_rresp<=inject_read&&read_position==3?2:0;
    m_ps_rlast<=read_left==1;m_ps_rvalid<=1;
   end
   if(m_pl_awvalid&&m_pl_awready)begin
    if(have_aw||m_pl_awaddr[3:0]||m_pl_awlen>=BURST||m_pl_awsize!=4||m_pl_awburst!=1||
       m_pl_awaddr[11:0]+(m_pl_awlen+1)*16>4096)$fatal(1,"PL burst layout/overlap");
    held_aw=m_pl_awaddr;aw_words=m_pl_awlen+1;have_aw=1;aw_count=aw_count+1;
   end
   if(m_pl_wvalid&&m_pl_wready)begin
    if(w_words>=16||write_last_seen||m_pl_wstrb!=16'hffff)$fatal(1,"PL W count/strobe");
    held_w[w_words]=m_pl_wdata;w_words=w_words+1;w_count=w_count+1;
    if(m_pl_wlast)write_last_seen=1;
   end
   if(have_aw&&write_last_seen&&!bdelay&&!m_pl_bvalid)begin
    if(w_words!=aw_words)$fatal(1,"WLAST does not match AWLEN");
    index=held_aw>=32'h21400000 ? (held_aw-32'h21400000)/16:(held_aw&32'hfffff)/16;
    slot=held_aw>=32'h100000 ? 1:0;
    if(index<0||index+w_words>WORDS)$fatal(1,"PL write outside frame");
    for(integer k=0;k<w_words;k++)begin
     if(held_w[k]!==expand(seen[index+k]))$fatal(1,"raw/snapshot changed pixels at %0d",index+k);
     if(held_aw>=32'h21400000)begin
      if(status[1:0]!=2)$fatal(1,"snapshot written without COPYING lease");
      snapshot_ram[index+k]=held_w[k];
     end else raw_ram[slot*WORDS+index+k]=held_w[k];
    end
    bdelay=17;
    m_pl_bresp<=(inject_b==1||(inject_b==2&&held_aw>=32'h21400000))?2:0;
    have_aw=0;write_last_seen=0;
   end
   if(bdelay>0)begin
    if(copy_done||present_valid||fb_swapped||(status[1:0]==3&&held_aw>=32'h21400000))$fatal(1,"frame/lease published before final B");
    bdelay=bdelay-1;if(bdelay==0)m_pl_bvalid<=1;
   end
   if(m_pl_bvalid&&m_pl_bready)begin m_pl_bvalid<=0;w_words=0;aw_words=0;b_count=b_count+1;end
  end
 end
 task reset_test;
  @(negedge clk);rst=1;swap_fb=0;request=0;release_snapshot=0;stall_read=0;stall_write=0;
  inject_read=0;inject_b=0;malformed=0;auto_ack=1;front_slot=0;fb_addr=32'h60000000;expected_source=fb_addr;fb_size=W*H;
  repeat(5)@(negedge clk);rst=0;repeat(3)@(negedge clk);
 endtask
 task command(input bit releasing,input integer value);
  @(negedge clk);command_token=value;request=!releasing;release_snapshot=releasing;
  @(negedge clk);request=0;release_snapshot=0;
 endtask
 task frame(input integer gen);
  @(negedge clk);generation=gen;swap_fb=1;
  wait(fb_swapped);@(negedge clk);front_slot=present_slot;swap_fb=0;
  repeat(4)@(negedge clk);
 endtask
 task fault_drained;
  wait(fault);wait(dut.state==7);wait(!read_left&&!m_ps_rvalid&&!m_pl_bvalid&&!bdelay);repeat(8)@(negedge clk);
  if(copy_count||present_count||fb_swapped||status[1:0])$fatal(1,"failed frame published after drain");
 endtask
 integer started,old_ar_count,old_aw_count,old_b_count;
 initial begin
  reset_test();command(0,11);started=cycle;frame(1);measured_cycles=cycle-started;
  if(fault||status!=3||ar_count!=(WORDS+BURST-1)/BURST||aw_count!=2*ar_count||r_count!=WORDS||w_count!=2*WORDS||b_count!=aw_count)
   $fatal(1,"full burst/frame accounting B=%0d",BURST);
  for(integer k=0;k<WORDS;k++)begin
   if(snapshot_ram[k]!==raw_ram[front_slot*WORDS+k])$fatal(1,"snapshot differs from raw frame");
   saved[k]=snapshot_ram[k];
  end
  $display("BRIDGE_BURST_MEASURE B=%0d pixels=%0d cycles=%0d AR=%0d AW=%0d",BURST,W*H,measured_cycles,ar_count,aw_count);
  if(STRESS)begin
   old_ar_count=ar_count;old_aw_count=aw_count;frame(2);
   if(status!=3||ar_count-old_ar_count!=(WORDS+BURST-1)/BURST||aw_count-old_aw_count!=(WORDS+BURST-1)/BURST)$fatal(1,"held lease blocked or recaptured");
   for(integer k=0;k<WORDS;k++)if(snapshot_ram[k]!==saved[k])$fatal(1,"held snapshot overwritten");
   command(1,10);if(status!=3)$fatal(1,"stale release accepted");command(1,11);
   command(0,12);@(negedge clk);swap_fb=1;generation=3;
   wait(m_pl_awvalid&&m_pl_awaddr==32'h21400000);@(negedge clk);stall_write=1;
   command(1,12);repeat(15)@(negedge clk);
   if(status[1:0]!=2||!status[8])$fatal(1,"in-flight cancellation did not retain lease");
   stall_write=0;wait(fb_swapped);@(negedge clk);swap_fb=0;repeat(4)@(negedge clk);
   if(status[1:0]||fault)$fatal(1,"canceled burst copy failed to drain");
   reset_test();command(0,20);inject_read=1;swap_fb=1;fault_drained();if(first_error!=2||aw_count||r_count!=BURST)$fatal(1,"RRESP drain");
   reset_test();command(0,21);malformed=1;swap_fb=1;fault_drained();if(first_error!=2||aw_count||r_count!=BURST/2)$fatal(1,"early RLAST drain");
   reset_test();command(0,22);malformed=2;swap_fb=1;fault_drained();if(first_error!=2||aw_count||r_count!=BURST+1)$fatal(1,"late RLAST drain");
   reset_test();command(0,23);inject_b=1;swap_fb=1;fault_drained();if(first_error!=3||write_errors!=1)$fatal(1,"raw B error");
   reset_test();command(0,24);inject_b=2;swap_fb=1;fault_drained();if(first_error!=3||b_count!=2)$fatal(1,"snapshot B error");
   reset_test();command(0,25);swap_fb=1;wait(r_count==1);@(negedge clk);stall_read=1;
   wait(fault);if(!m_ps_rready||first_error!=4)$fatal(1,"read timeout withdrew RREADY");
   stall_read=0;fault_drained();if(r_count!=BURST)$fatal(1,"timeout did not drain full read");
   reset_test();command(0,26);swap_fb=1;wait(w_count==1);@(negedge clk);stall_write=1;
   wait(fault);if(!m_pl_wvalid||first_error!=4)$fatal(1,"write timeout withdrew WVALID");
   stall_write=0;fault_drained();if(w_count!=BURST||b_count!=1)$fatal(1,"timeout did not drain full write");
   reset_test();swap_fb=1;wait(m_ps_arvalid&&m_ps_arready);@(negedge clk);fb_addr=32'h60212340;
   wait(copy_done);#1;if(completed_source_base!=32'h60000000)$fatal(1,"source metadata followed live register");
   wait(fb_swapped);@(negedge clk);swap_fb=0;
   reset_test();fb_size=W*H-1;swap_fb=1;wait(fault);if(first_error!=1||ar_count||aw_count)$fatal(1,"bad size accepted");
   reset_test();fb_addr=32'hdeadbeef;swap_fb=1;wait(fault);if(first_error!=1||ar_count||aw_count)$fatal(1,"bad address accepted");
   reset_test();if(status||token||fault)$fatal(1,"reset retained state");
  end
  finished=1;
 end
endmodule

module tb_bridge_burst;
 wire fast_done,slow_done,stress_done;wire [31:0] fast_cycles,slow_cycles,stress_cycles;
 bridge_burst_case #(.BURST(16)) fast(fast_done,fast_cycles);
 bridge_burst_case #(.BURST(1)) control(slow_done,slow_cycles);
 bridge_burst_case #(.BURST(16),.W(20),.H(7),.STRESS(1)) stress(stress_done,stress_cycles);
 initial begin
  wait(fast_done&&slow_done&&stress_done);
  if(slow_cycles<3*fast_cycles)$fatal(1,"burst optimization lost expected transaction benefit");
  $display("PASS bridge burst: 96000 pixels, raw+immutable snapshot, AR/AW 16x reduction, tails, 4KiB, stalls, cancel, R/B errors, malformed RLAST and timeout drain; cycles single=%0d burst16=%0d",slow_cycles,fast_cycles);
  $finish;
 end
 initial begin #100000000;$fatal(1,"burst bridge watchdog");end
endmodule
