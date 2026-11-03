`timescale 1ns/1ps
module tb_cnn_inplace_r1;
 parameter W=7,H=5;
 localparam N=W*H;
 reg clk=0,rst=1;always #5 clk=~clk;
 reg cfg_restart=0,cfg_valid=0,cfg_commit=0,start=0;
 reg [11:0] cfg_addr=0;reg [31:0] cfg_data=0;
 wire cfg_ready,model_valid,busy,fault,done;
 wire [31:0] compute_cycles;
 reg [63:0] s_data=0;reg s_valid=0,s_last=0;wire s_ready;
 wire [63:0] m_data;wire m_valid,m_last;reg m_ready=0;
 rix_cnn_engine #(.WIDTH(W),.HEIGHT(H)) dut(.*);
 reg [31:0] config_words[0:1775];reg [63:0] inputs[0:N-1],golden[0:N-1];
 integer i,seed=4863,checks=0,cycle=0,out_count;
 reg stalled=0;reg [63:0] held;reg held_last;
 string vector_dir,model_name,size_name;
 reg [63:0] layer_golden[0:3*N-1];
 reg check_layer=0,frame_compare_enable=0;integer completed_layer=0,j,layer_checks=0;
 always @(posedge clk) begin
  check_layer<=frame_compare_enable && !rst && dut.state==8 && dut.y==H-1 && dut.copy_tail;
  completed_layer<=dut.layer;
 end
 always @(negedge clk) if(check_layer&&!rst&&frame_compare_enable) begin
  for(j=0;j<N;j=j+1)
   if(dut.frame_storage.memory[j]!==layer_golden[completed_layer*N+j])
    $fatal(1,"layer %0d vector %0d mismatch",completed_layer,j);
  layer_checks=layer_checks+N;
 end
 always @(posedge clk) if(!rst&&dut.frame_write&&dut.frame_read_enable)
  $fatal(1,"single-port frame RAM read/write overlap");
 always @(posedge clk) begin
  cycle<=cycle+1;
  if(cycle>18000000) $fatal(1,"watchdog");
  if(rst) stalled<=0;
  else begin
   if(stalled && (!m_valid || m_data!==held || m_last!==held_last)) $fatal(1,"output changed under backpressure");
   stalled<=m_valid&&!m_ready;held<=m_data;held_last<=m_last;
  end
 end
 task tick;begin @(negedge clk);end endtask
 task reset_core;begin rst=1;frame_compare_enable=0;s_valid=0;m_ready=0;start=0;cfg_valid=0;cfg_commit=0;repeat(4)tick();rst=0;tick();end endtask
 task load_model(input string name);
  begin
   $readmemh({vector_dir,"/",name,"-config.hex"},config_words);
   cfg_restart=1;tick();cfg_restart=0;
   for(i=0;i<1776;i=i+1) begin
    if(!cfg_ready) $fatal(1,"config not ready");
    cfg_valid=1;cfg_addr=i<1728?i:(i<1752?2048+i-1728:2080+i-1752);cfg_data=config_words[i];tick();
   end
   cfg_valid=0;cfg_commit=1;tick();cfg_commit=0;tick();
   if(!model_valid||fault) $fatal(1,"model not committed");
   checks=checks+1;
  end
 endtask
 task run_frame(input string name,input string scale);
  integer idx;
  begin
   $readmemh({vector_dir,"/",name,"-",scale,"-input.hex"},inputs);
   $readmemh({vector_dir,"/",name,"-",scale,"-output.hex"},golden);
   $readmemh({vector_dir,"/",name,"-",scale,"-layers.hex"},layer_golden);
   frame_compare_enable=1;start=1;tick();start=0;
   for(idx=0;idx<N;idx=idx+1) begin
    if(!s_ready) $fatal(1,"input not ready");
    seed=(seed*1103515245+12345)&32'h7fffffff;
    if(seed%3==0) begin s_valid=0;tick();end
    s_valid=1;s_data=inputs[idx];s_last=idx==N-1;tick();
   end
   s_valid=0;s_last=0;
   // A model write while busy must not be accepted or change the active model.
   cfg_valid=1;cfg_data=32'hbad;cfg_addr=0;tick();cfg_valid=0;
   if(cfg_ready) $fatal(1,"model writable during inference");
   out_count=0;
   while(out_count<N) begin
    seed=(seed*1103515245+12345)&32'h7fffffff;m_ready=seed%4!=0;
    @(posedge clk);
    if(m_valid&&m_ready) begin
     if(m_data!==golden[out_count]) $fatal(1,"%s pixel %d got %h expected %h",name,out_count,m_data,golden[out_count]);
     if(m_last!=(out_count==N-1)) $fatal(1,"bad TLAST");
     out_count=out_count+1;checks=checks+1;
    end
    tick();
   end
   m_ready=0;tick();if(busy||fault) $fatal(1,"did not finish cleanly");
   if(compute_cycles!=30*N+21*H)$fatal(1,"pipeline cycle count %0d expected %0d",compute_cycles,30*N+21*H);
   $display("CNN_FRAME_PASS model=%s pixels=%0d cycles=%0d",name,N,compute_cycles);
   frame_compare_enable=0;
  end
 endtask
 initial begin
  vector_dir=$sformatf("../vectors/%0dx%0d",W,H);
  size_name="random";
  reset_core();
  start=1;tick();start=0;if(!fault||busy) $fatal(1,"uninitialized model accepted");
  reset_core();
  cfg_commit=1;tick();cfg_commit=0;if(!fault||model_valid) $fatal(1,"incomplete model accepted");
  reset_core();load_model("oil");run_frame("oil",size_name);run_frame("oil",size_name);
  load_model("anime");run_frame("anime",size_name);
  if(N==15360) begin
   load_model("oil");run_frame("oil","real8");run_frame("oil","real22");run_frame("oil","real28");
   load_model("anime");run_frame("anime","real8");run_frame("anime","real22");run_frame("anime","real28");
   load_model("stress");run_frame("stress","random");
  end
  if(N<100) begin
   load_model("stress");run_frame("stress","random");
   if(N>1)begin
    start=1;tick();start=0;s_valid=1;s_last=1;tick();s_valid=0;s_last=0;
    if(!fault||busy) $fatal(1,"early TLAST accepted");
   end
   reset_core();load_model("anime");start=1;tick();start=0;
   for(i=0;i<N;i=i+1)begin s_valid=1;s_last=0;tick();end s_valid=0;
   if(!fault||busy) $fatal(1,"missing TLAST accepted");
   reset_core();load_model("oil");start=1;tick();start=0;s_valid=1;tick();reset_core();
   if(busy||model_valid||m_valid) $fatal(1,"reset did not discard frame/model");
   load_model("oil");start=1;tick();start=0;
   for(i=0;i<N;i=i+1)begin s_valid=1;s_last=i==N-1;tick();end
   s_valid=0;s_last=0;repeat(17)tick();reset_core();
   load_model("anime");run_frame("anime","random");
   // Reset during the new BRAM-copy phase must discard all pending writes.
   start=1;tick();start=0;
   for(i=0;i<N;i=i+1)begin s_valid=1;s_data=inputs[i];s_last=i==N-1;tick();end
   s_valid=0;s_last=0;
   while(dut.state!=7)tick();reset_core();
   if(busy||model_valid||m_valid) $fatal(1,"copy reset failed");
   load_model("oil");run_frame("oil","random");
  end
  $display("PASS CNN_INPLACE_R1 W=%0d H=%0d values=%0d layer_values=%0d",W,H,checks,layer_checks);
  $finish;
 end
endmodule

module tb_cnn_inplace_r1_full; tb_cnn_inplace_r1 #(.W(160),.H(96)) test(); endmodule
module tb_cnn_inplace_r1_one; tb_cnn_inplace_r1 #(.W(1),.H(1)) test(); endmodule
module tb_cnn_inplace_r1_row; tb_cnn_inplace_r1 #(.W(7),.H(1)) test(); endmodule
module tb_cnn_inplace_r1_col; tb_cnn_inplace_r1 #(.W(1),.H(5)) test(); endmodule
module tb_cnn_inplace_r1_two; tb_cnn_inplace_r1 #(.W(2),.H(2)) test(); endmodule
