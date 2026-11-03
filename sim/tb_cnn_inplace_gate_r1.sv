`timescale 1ns/1ps
// Full-size functional-netlist smoke: reaches the output through real model
// and frame loading. Detects synthesis trimming or RAM semantic mismatches.
module tb_cnn_inplace_gate_r1;
 localparam N=160*96;
 reg clk=0,rst=1;always #5 clk=~clk;
 reg cfg_restart=0,cfg_valid=0,cfg_commit=0,start=0;
 reg [11:0] cfg_addr=0;reg [31:0] cfg_data=0;
 wire cfg_ready,model_valid,busy,fault,done;
 wire [31:0] compute_cycles;
 reg [63:0] s_data=0;reg s_valid=0,s_last=0;wire s_ready;
 wire [63:0] m_data;wire m_valid,m_last;reg m_ready=0;
 rix_cnn_engine dut(.*);
 reg [31:0] config_words[0:1775];
 reg [63:0] inputs[0:N-1],golden[0:N-1];
 integer i,cycles=0,outputs=0;
 always @(posedge clk)begin cycles<=cycles+1;if(cycles>600000)$fatal(1,"netlist watchdog");end
 task tick;begin @(negedge clk);end endtask
 initial begin
  $readmemh("../vectors/160x96/oil-config.hex",config_words);
  $readmemh("../vectors/160x96/oil-real28-input.hex",inputs);
  $readmemh("../vectors/160x96/oil-real28-output.hex",golden);
  // Allow global startup reset in the device primitive simulation to finish.
  repeat(20)tick();rst=0;tick();cfg_restart=1;tick();cfg_restart=0;
  for(i=0;i<1776;i=i+1)begin
   if(!cfg_ready)$fatal(1,"netlist configuration not ready");
   cfg_valid=1;cfg_addr=i<1728?i:(i<1752?2048+i-1728:2080+i-1752);cfg_data=config_words[i];tick();
  end
  cfg_valid=0;cfg_commit=1;tick();cfg_commit=0;tick();
  if(!model_valid||fault)$fatal(1,"netlist model commit failed");
  start=1;tick();start=0;
  for(i=0;i<N;i=i+1)begin
   if(!s_ready)$fatal(1,"netlist input not ready");
   s_valid=1;s_data=inputs[i];s_last=i==N-1;tick();
  end
  s_valid=0;s_last=0;m_ready=1;
  while(outputs<N)begin
   @(posedge clk);
   if(m_valid)begin
    if(m_data!==golden[outputs])$fatal(1,"netlist vector %0d mismatch",outputs);
    if(m_last!=(outputs==N-1))$fatal(1,"netlist TLAST mismatch");
    outputs=outputs+1;
   end
   tick();
  end
  tick();if(busy||fault||compute_cycles!=462816)$fatal(1,"netlist completion/profile mismatch");
  $display("PASS CNN_INPLACE_GATE_R1 vectors=%0d cycles=%0d",outputs,compute_cycles);
  $finish;
 end
endmodule
