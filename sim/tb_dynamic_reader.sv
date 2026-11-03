`timescale 1ns/1ps
module tb_dynamic_reader;
 reg clk=0;always #5 clk=~clk;
 reg rst=1,start=0,abort=0,ready=0;reg [31:0] frame_base=0;reg [19:0] frame_pixels=96000;
 wire idle,done,aborted,error,valid;wire [127:0] data;wire [31:0] m_axi_araddr;wire [7:0] m_axi_arlen;wire [2:0] m_axi_arsize;wire [1:0] m_axi_arburst;wire m_axi_arvalid,m_axi_rready;
 reg m_axi_arready=0,m_axi_rlast=0,m_axi_rvalid=0;reg [127:0] m_axi_rdata=0;reg [1:0] m_axi_rresp=0;
 integer beats_left=0,delivered=0,cycles=0;reg stall=0,consumer_stall=0;reg [31:0] expected_addr=0;
 rix_frame_reader_dynamic dut(.*);
 always @(negedge clk)begin cycles=cycles+1;ready=!consumer_stall&&cycles%5!=0;m_axi_arready=!stall&&beats_left==0&&cycles%3!=0;end
 always @(posedge clk)if(!rst)begin
  if(m_axi_arvalid&&m_axi_arready)begin
   if(m_axi_araddr!==expected_addr||m_axi_arsize!=4||m_axi_arburst!=1||((m_axi_araddr&4095)+(m_axi_arlen+1)*16)>4096)$fatal(1,"AXI burst address or boundary");
   expected_addr<=expected_addr+(m_axi_arlen+1)*16;beats_left<=m_axi_arlen+1;
  end
  if(m_axi_rvalid&&m_axi_rready)begin beats_left<=beats_left-1;m_axi_rvalid<=0;end
  if(valid&&ready)delivered<=delivered+1;
  if(beats_left>0&&!m_axi_rvalid&&cycles%4!=0)begin m_axi_rvalid<=1;m_axi_rlast<=beats_left==1;end
 end
 task launch(input [31:0] base,input [19:0] pixels);
 begin @(negedge clk);frame_base=base;frame_pixels=pixels;expected_addr=base;delivered=0;start=1;@(negedge clk);start=0;end endtask
 initial begin
 repeat(5)@(negedge clk);rst=0;
 launch(32'hff0,96000);wait(done);if(delivered!=24000)$fatal(1,"LR frame size");
 launch(32'h21000000,384000);wait(done);if(delivered!=96000)$fatal(1,"HR frame size");
 launch(32'h21200000,15360);wait(done);if(delivered!=3840)$fatal(1,"neural frame size");
 consumer_stall=1;launch(32'h21200000,15360);wait(dut.state==5);repeat(10)@(negedge clk);
 if(beats_left!=0||delivered!=0||m_axi_arvalid||m_axi_rready)$fatal(1,"neural buffer did not release the DDR channel");
 abort=1;wait(aborted);@(negedge clk);abort=0;if(!idle||delivered!=0)$fatal(1,"neural buffered abort published pixels");
 launch(32'h21200000,15360);wait(dut.received>10);@(negedge clk);abort=1;wait(aborted);@(negedge clk);abort=0;
 if(!idle||beats_left!=0||delivered!=0)$fatal(1,"neural outstanding burst abort did not drain");
 consumer_stall=0;
 launch(32'h3ffff000,384000);#1;if(!error||!idle)$fatal(1,"out of range accepted");
 launch(32'h21000001,384000);#1;if(!error||!idle)$fatal(1,"unaligned frame accepted");
 launch(0,4);#1;if(!error||!idle)$fatal(1,"unsupported size accepted");
 stall=1;launch(32'h21000000,384000);wait(m_axi_arvalid);@(negedge clk);abort=1;repeat(5)begin @(negedge clk);if(!m_axi_arvalid)$fatal(1,"ARVALID withdrawn on abort");end
 stall=0;wait(aborted);@(negedge clk);abort=0;if(delivered!=0||!idle)$fatal(1,"cancelled frame published");
 $display("PASS dynamic reader LR/HR lengths, backpressure, 4K boundary, illegal size/address, stalled abort drain");$finish;
 end
 initial begin #20000000;$fatal(1,"timeout");end
endmodule
