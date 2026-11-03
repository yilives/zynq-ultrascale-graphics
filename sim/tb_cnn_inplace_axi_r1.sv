`timescale 1ns/1ps
// Isolated extension regression: both output protocols share one retirement
// path. No force/release of the core; OUTREAD is reached via real handshakes.
module tb_cnn_inplace_axi_r1;
 parameter W=7,H=5;
 localparam N=W*H;
 reg s_axi_aclk=0;always #5 s_axi_aclk=~s_axi_aclk;
 reg s_axi_aresetn=0;
 reg [15:0] s_axi_awaddr=0,s_axi_araddr=0;
 reg [2:0] s_axi_awprot=0,s_axi_arprot=0;
 reg s_axi_awvalid=0,s_axi_wvalid=0,s_axi_bready=0,s_axi_arvalid=0,s_axi_rready=0;
 reg [31:0] s_axi_wdata=0;reg [3:0] s_axi_wstrb=15;
 wire s_axi_awready,s_axi_wready,s_axi_bvalid,s_axi_arready,s_axi_rvalid;
 wire [1:0] s_axi_bresp,s_axi_rresp;wire [31:0] s_axi_rdata;
 rix_cnn_axi #(.WIDTH(W),.HEIGHT(H)) dut(.*);
 reg [31:0] config_words[0:1775];reg [63:0] inputs[0:N-1],golden[0:N-1];
 integer i,transactions=0,cycle=0,turn=0,pixels=0,invalid_reads=0,outread_probes=0;
 integer stalled_reads=0,pop_count=0,frames=0;
 reg [31:0] value;
 string vector_dir,size_name;
 always @(posedge s_axi_aclk) begin
  cycle<=cycle+1;if(cycle>10000000)$fatal(1,"atomic AXI watchdog");
  if(s_axi_aresetn&&dut.m_ready) begin
   if(!dut.m_valid)$fatal(1,"pop without valid output");
   pop_count<=pop_count+1;
  end
 end
 task tick;begin @(negedge s_axi_aclk);end endtask
 task write_reg(input [15:0] address,input [31:0] data,input [1:0] response);
  reg [1:0] saved;
  begin
   s_axi_bready=0;
   fork
    begin
     repeat(turn%3)tick();s_axi_awaddr=address;s_axi_awvalid=1;
     @(posedge s_axi_aclk);while(!s_axi_awready)@(posedge s_axi_aclk);
     tick();s_axi_awvalid=0;
    end
    begin
     repeat((turn+1)%3)tick();s_axi_wdata=data;s_axi_wvalid=1;
     @(posedge s_axi_aclk);while(!s_axi_wready)@(posedge s_axi_aclk);
     tick();s_axi_wvalid=0;
    end
   join
   while(!s_axi_bvalid)tick();saved=s_axi_bresp;
   repeat(turn%4)begin tick();if(!s_axi_bvalid||s_axi_bresp!==saved)$fatal(1,"B changed under stall");end
   if(saved!==response)$fatal(1,"write %h response %h expected %h",address,saved,response);
   s_axi_bready=1;tick();s_axi_bready=0;tick();turn=turn+1;transactions=transactions+1;
  end
 endtask
 // Return on the first negedge after R acceptance. The very next call can
 // issue AR while the real core is in OUTREAD, exercising invalid polling.
 task read_reg(input [15:0] address,input [1:0] response,input integer stalls,output [31:0] data);
  reg [31:0] saved,old_index;reg [1:0] saved_resp;reg should_pop;
  integer old_pops;
  begin
   s_axi_araddr=address;s_axi_arvalid=1;s_axi_rready=0;
   @(posedge s_axi_aclk);while(!s_axi_arready)@(posedge s_axi_aclk);
   tick();s_axi_arvalid=0;while(!s_axi_rvalid)tick();
   saved=s_axi_rdata;saved_resp=s_axi_rresp;old_index=dut.output_index;old_pops=pop_count;
   should_pop=(address=='h18&&response==0)||(address=='h40&&saved[31]);
   repeat(stalls)begin
    tick();if(!s_axi_rvalid||s_axi_rdata!==saved||s_axi_rresp!==saved_resp)$fatal(1,"R changed under stall");
    if(dut.output_index!==old_index||pop_count!=old_pops)$fatal(1,"pixel popped before R handshake");
    if(dut.s_axi_arready)$fatal(1,"second AR accepted while response stalled");
   end
   if(stalls>0)stalled_reads=stalled_reads+1;
   if(saved_resp!==response)$fatal(1,"read %h response %h expected %h",address,saved_resp,response);
   data=saved;s_axi_rready=1;tick();s_axi_rready=0;
   if(dut.output_index!==old_index+should_pop||pop_count!=old_pops+should_pop)$fatal(1,"R handshake did not retire exactly once address=%h",address);
   if(address=='h40&&!saved[31])invalid_reads=invalid_reads+1;
   turn=turn+1;transactions=transactions+1;
  end
 endtask
 task wait_valid;
  begin
   read_reg('h0c,0,turn%3,value);
   while(!value[2])read_reg('h0c,0,0,value);
  end
 endtask
 task run_model(input string name,input integer protocol);
  reg [31:0] item;
  begin
   $readmemh({vector_dir,"/",name,"-config.hex"},config_words);
   $readmemh({vector_dir,"/",name,"-",size_name,"-input.hex"},inputs);
   $readmemh({vector_dir,"/",name,"-",size_name,"-output.hex"},golden);
   write_reg('h08,4,0);
   for(i=0;i<1776;i=i+1)begin
    write_reg('h20,i<1728?i:(i<1752?2048+i-1728:2080+i-1752),0);write_reg('h24,config_words[i],0);
   end
   write_reg('h08,8,0);read_reg('h0c,0,1,value);if(!value[3]||value[4])$fatal(1,"bad model status");
   write_reg('h08,1,0);
   read_reg('h40,0,7,value);if(value!==0)$fatal(1,"LOAD must return invalid/zero without pop");
   for(i=0;i<N;i=i+1)write_reg('h10,inputs[i][23:0]^24'h808080,0);
   read_reg('h40,0,3,value);if(value!==0)$fatal(1,"RUN must return invalid/zero without pop");
   write_reg('h20,0,2);write_reg('h10,0,2);wait_valid();
   for(i=0;i<N;i=i+1)begin
    if(protocol==0||(protocol==2&&i%3==0))begin
     wait_valid();read_reg('h18,0,turn%5,item);
    end else begin
     read_reg('h40,0,turn%7,item);
     while(!item[31])read_reg('h40,0,0,item);
     if(item[30]||item[29]!=(i==N-1)||item[28:24]!=0)$fatal(1,"bad atomic flags pixel=%0d",i);
    end
    if(item[23:0]!==(golden[i][23:0]^24'h808080))$fatal(1,"%s protocol=%0d pixel=%0d got=%h expected=%h",name,protocol,i,item[23:0],golden[i][23:0]^24'h808080);
    pixels=pixels+1;
    if(i!=N-1)begin
     if(dut.engine.state!==5)$fatal(1,"retirement did not enter real OUTREAD");
     read_reg('h40,0,turn%4,value);
     if(value!==0)$fatal(1,"OUTREAD atomic polling must return invalid without consuming next pixel");
     outread_probes=outread_probes+1;
    end
   end
   frames=frames+1;
   read_reg('h0c,0,3,value);if(value[0]||value[4])$fatal(1,"bad completed status");
   // done_sticky is registered one edge after the final core handshake.
   while(!value[5])read_reg('h0c,0,0,value);
   read_reg('h28,0,0,value);if(value!=30*N+21*H)$fatal(1,"bad compute cycle counter");
   read_reg('h2c,0,0,value);if(value!=frames)$fatal(1,"bad frame counter");
   read_reg('h30,0,0,value);if(value!=N)$fatal(1,"bad input count");
   read_reg('h34,0,0,value);if(value!=N)$fatal(1,"bad output count");
   read_reg('h18,2,4,value);read_reg('h40,0,7,value);if(value!==0)$fatal(1,"IDLE atomic read must be invalid");
   $display("ATOMIC_CNN_FRAME_PASS model=%s protocol=%0d pixels=%0d cycles=%0d",name,protocol,N,30*N+21*H);
  end
 endtask
 initial begin
  vector_dir=$sformatf("../vectors/%0dx%0d",W,H);
  if($value$plusargs("VECTORS=%s",vector_dir))begin end
  size_name="random";
  repeat(5)tick();s_axi_aresetn=1;tick();
  read_reg(0,0,0,value);if(value!=32'h4e495031)$fatal(1,"NIP1 magic mismatch");
  read_reg('h38,0,0,value);if(value!=30*N+21*H)$fatal(1,"bad compute profile");
  read_reg('h3c,0,0,value);if(value!=13)$fatal(1,"bad new capability");
  read_reg('h44,0,0,value);if(value!=32'h00030001)$fatal(1,"bad adapter register ABI");
  read_reg(4,0,0,value);if(value!={(16'(H)),(16'(W))})$fatal(1,"bad dimensions");
  read_reg('h40,0,9,value);if(value!==0)$fatal(1,"reset invalid atomic read");
  write_reg(8,1,2);read_reg('h18,2,3,value);write_reg('hfffc,0,2);
  s_axi_wstrb=1;write_reg('h08,2,2);s_axi_wstrb=15;
  write_reg(8,8,0);read_reg('h40,0,4,value);if(value!==32'h40000000)$fatal(1,"atomic fault must be visible without a pop");
  write_reg(8,2,0);read_reg('h40,0,2,value);if(value!==0)$fatal(1,"reset must clear atomic fault flag");
  run_model("oil",1);run_model("anime",2);
  if(N==35)begin run_model("oil",0);run_model("anime",1);end
  if(pop_count!=pixels||invalid_reads<outread_probes||outread_probes!=frames*(N-1)||stalled_reads==0)$fatal(1,"coverage/pop accounting failed");
  write_reg(8,2,0);read_reg('h0c,0,0,value);if(value[3]||value[0])$fatal(1,"soft reset did not discard model");
  read_reg('h40,0,5,value);if(value!==0)$fatal(1,"soft reset must invalidate atomic port");
  $display("PASS CNN_INPLACE_AXI_R1 frames=%0d pixels=%0d pops=%0d invalid_reads=%0d outread_probes=%0d stalled_reads=%0d transactions=%0d",frames,pixels,pop_count,invalid_reads,outread_probes,stalled_reads,transactions);
  $finish;
 end
endmodule
module tb_cnn_inplace_axi_r1_full;
 tb_cnn_inplace_axi_r1 #(.W(160),.H(96)) test();
endmodule
