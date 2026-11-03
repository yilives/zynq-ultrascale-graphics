`timescale 1ns/1ps
// Real upstream CommandParser -> real frame bridge, old and corrected feedback.
module swap_fence_case #(parameter LEGACY=0)(output reg finished=0);
 localparam FRAMES=32;
 reg clk=0,rst=1;always #5 clk=~clk;
 integer cycle=0,accepted=0,early=0;
 reg valid=0;reg [31:0] data=0;wire cmd_ready,apply,swap,memset_cmd,commit_cmd,read_cmd;
 wire request=apply&&swap;
 wire bridge_done,fence_ready;
 wire feedback=LEGACY?(!request||bridge_done):fence_ready;
 reg buffer_ready=1,previous_buffer_apply=0;integer buffer_delay=0;
 wire buffer_apply=apply&&(memset_cmd||commit_cmd||read_cmd);
 rix_swap_fence fence(.clk(clk),.rst(rst),.request(request),.completed(bridge_done),.ready(fence_ready));
 CommandParser #(.CMD_STREAM_WIDTH(32),.FB_SIZE_IN_PIXEL_LG(20)) parser(
  .aclk(clk),.resetn(!rst),.s_cmd_axis_tvalid(valid),.s_cmd_axis_tready(cmd_ready),.s_cmd_axis_tdata(data),
  .m_cmd_fog_axis_tready(1'b1),.m_cmd_rasterizer_axis_tready(1'b1),.m_cmd_tmu0_axis_tready(1'b1),
  .m_cmd_tmu1_axis_tready(1'b1),.m_cmd_config_axis_tready(1'b1),
  .rasterizerRunning(1'b0),.pixelInPipeline(1'b0),.dataInTriangleInterpolator(1'b0),
  .colorBufferApply(apply),.colorBufferApplied(buffer_ready&&feedback),.colorBufferCmdSwap(swap),
  .colorBufferCmdMemset(memset_cmd),.colorBufferCmdCommit(commit_cmd),.colorBufferCmdRead(read_cmd),
  .depthBufferApplied(1'b1),.stencilBufferApplied(1'b1));
 wire [31:0] araddr,awaddr,id,swaps,copies,presents,re,we,to;
 wire [7:0] arlen,awlen;wire arv,rr,awv,wv,wl,br,pv,slot,fault;
 wire [127:0] wd;wire [15:0] ws;
 reg rv=0,rl=0,bv=0,front=0;
 reg [63:0] rd=0;
 integer read_left=0,read_delay=0,write_beats=0,aw_beats=0,bdelay=0,pdelay=0;
 reg got_aw=0,got_last=0;
 wire arready=cycle%3!=0,awready=cycle%5!=0,wready=cycle%7!=0;
 wire pack=pv&&pdelay>=40+(id%7)*3;
 rix_frame_bridge #(.WIDTH(8),.HEIGHT(4),.PS_GFX_BASE(32'h60000000),.TIMEOUT_CYCLES(100000)) bridge(
  .clk(clk),.rst(rst),.enable(1'b1),.mig_ready(1'b1),.lcd_running(1'b1),
  .swap_fb(request),.fb_addr(32'h60000000),.fb_size(20'd32),.fb_swapped(bridge_done),
  .front_slot(front),.present_valid(pv),.present_slot(slot),.frame_id(id),.present_ack(pack),.presented_id(id),
  .fault(fault),.snapshot_pending(1'b0),.swap_count(swaps),.copy_count(copies),.present_count(presents),
  .read_errors(re),.write_errors(we),.timeouts(to),
  .m_ps_araddr(araddr),.m_ps_arlen(arlen),.m_ps_arvalid(arv),.m_ps_arready(arready),
  .m_ps_rdata(rd),.m_ps_rresp(2'b0),.m_ps_rlast(rl),.m_ps_rvalid(rv),.m_ps_rready(rr),
  .m_pl_awaddr(awaddr),.m_pl_awlen(awlen),.m_pl_awvalid(awv),.m_pl_awready(awready),
  .m_pl_wdata(wd),.m_pl_wstrb(ws),.m_pl_wlast(wl),.m_pl_wvalid(wv),.m_pl_wready(wready),
  .m_pl_bresp(2'b0),.m_pl_bvalid(bv),.m_pl_bready(br));
 always @(posedge clk) begin
  cycle<=cycle+1;
  if(!rst) begin
   if(valid&&cmd_ready) begin
    if(data[2]) accepted<=accepted+1;
    if(bridge.state!=0&&bridge.state!=6) early<=early+1;
   end
   if(buffer_apply&&!previous_buffer_apply) begin buffer_ready<=0;buffer_delay<=5;end
   else if(buffer_delay>0) begin
    buffer_delay<=buffer_delay-1;if(buffer_delay==1)buffer_ready<=1;
   end
   previous_buffer_apply<=buffer_apply;
   if(arv&&arready) begin
    if(read_left||rv)$fatal(1,"overlapping reads");read_left<=arlen+1;read_delay<=9;
   end
   if(rv&&rr)begin rv<=0;read_left<=read_left-1;end
   if(read_delay>0)read_delay<=read_delay-1;
   else if(read_left&&!rv&&cycle%4!=0)begin rv<=1;rl<=read_left==1;rd<=64'hf81f07e0001fffff;end
   if(awv&&awready)begin got_aw<=1;aw_beats<=awlen+1;end
   if(wv&&wready)begin write_beats<=write_beats+1;if(wl)got_last<=1;end
   if(got_aw&&got_last&&!bdelay&&!bv)begin
    if(write_beats!=aw_beats)$fatal(1,"write length");bdelay<=11;
   end
   if(bdelay>0)begin bdelay<=bdelay-1;if(bdelay==1)bv<=1;end
   if(bv&&br)begin bv<=0;got_aw<=0;got_last<=0;aw_beats<=0;write_beats<=0;end
   if(pv)pdelay<=pdelay+1;else pdelay<=0;
   if(pack)front<=slot;
   if(fault||re||we||to)$fatal(1,"bridge error");
  end
 end
 task send(input [31:0] command);
  @(negedge clk);data=command;valid=1;
  do @(posedge clk);while(!cmd_ready);
  @(negedge clk);valid=0;
 endtask
 initial begin
  repeat(6)@(negedge clk);rst=0;
  send(32'h20002012); // clear: must complete without requiring a swap ack
  for(integer n=0;n<FRAMES;n++) begin
   send(32'h20002094); // color swap + vsync, 32 pixels
   send(32'h20002011); // commit after each swap: cannot start during source copy
  end
  send(32'h20002018); // readback/autoload must still complete
  repeat(1200)@(negedge clk);
  if(accepted!=FRAMES)$fatal(1,"driver missed commands");
  if(LEGACY) begin
   if(swaps>=FRAMES||!early)$fatal(1,"legacy defect was not reproduced");
   $display("REPRODUCED LEGACY_SWAP_LOSS requested=%0d accepted=%0d early_commands=%0d",FRAMES,swaps,early);
  end else begin
   if(swaps!=FRAMES||copies!=FRAMES||presents!=FRAMES||early)$fatal(1,"fixed swap accounting req=%0d swap=%0d copy=%0d present=%0d early=%0d",FRAMES,swaps,copies,presents,early);
   $display("PASS SWAP_FENCE requested=%0d swaps=%0d copies=%0d presents=%0d early=0",FRAMES,swaps,copies,presents);
  end
  finished=1;
 end
 initial begin repeat(100000)@(posedge clk);$fatal(1,"parser/bridge timeout LEGACY=%0d",LEGACY);end
endmodule
module tb_swap_fence;
 wire old_done,new_done;
 swap_fence_case #(.LEGACY(1)) old_case(old_done);
 swap_fence_case #(.LEGACY(0)) new_case(new_done);
 reg clk=0,rst=1,req=0,ack=0;wire ready;reg extra_done=0;
 always #5 clk=~clk;
 rix_swap_fence held(.clk(clk),.rst(rst),.request(req),.completed(ack),.ready(ready));
 initial begin
  repeat(3)@(negedge clk);rst=0;@(negedge clk);if(!ready)$fatal(1,"idle clear ready");
  req=1;repeat(3)@(negedge clk);if(ready)$fatal(1,"early held ack");
  ack=1;@(negedge clk);ack=0;repeat(4)@(negedge clk);if(!ready)$fatal(1,"held completion lost");
  req=0;repeat(2)@(negedge clk);req=1;repeat(2)@(negedge clk);req=0;
  repeat(20)@(negedge clk);if(ready)$fatal(1,"pulse withdrawal acknowledged");
  rst=1;repeat(2)@(negedge clk);rst=0;@(negedge clk);if(!ready)$fatal(1,"reset did not clear pending fence");
  extra_done=1;
 end
 initial begin wait(old_done&&new_done&&extra_done);$display("PASS SWAP_FENCE_REGRESSION legacy_reproduced=1 real_parser=1 real_bridge=1");$finish;end
endmodule
