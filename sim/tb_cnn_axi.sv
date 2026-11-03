`timescale 1ns/1ps
module tb_cnn_axi;
 reg s_axi_aclk=0;always #5 s_axi_aclk=~s_axi_aclk;
 reg s_axi_aresetn=0;
 reg [15:0] s_axi_awaddr=0,s_axi_araddr=0;
 reg [2:0] s_axi_awprot=0,s_axi_arprot=0;
 reg s_axi_awvalid=0,s_axi_wvalid=0,s_axi_bready=0,s_axi_arvalid=0,s_axi_rready=0;
 reg [31:0] s_axi_wdata=0;reg [3:0] s_axi_wstrb=15;
 wire s_axi_awready,s_axi_wready,s_axi_bvalid,s_axi_arready,s_axi_rvalid;
 wire [1:0] s_axi_bresp,s_axi_rresp;wire [31:0] s_axi_rdata;
 rix_cnn_axi #(.WIDTH(7),.HEIGHT(5)) dut(.*);
 reg [31:0] config_words[0:1775];reg [63:0] inputs[0:34],golden[0:34];
 integer i,transactions=0,cycle=0,turn=0;reg [31:0] value;
 always @(posedge s_axi_aclk) begin cycle<=cycle+1;if(cycle>500000) $fatal(1,"AXI watchdog");end
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
 task read_reg(input [15:0] address,input [1:0] response,output [31:0] data);
  reg [31:0] saved;reg [1:0] saved_resp;reg [31:0] old_index;
  begin
   s_axi_araddr=address;s_axi_arvalid=1;s_axi_rready=0;
   @(posedge s_axi_aclk);while(!s_axi_arready)@(posedge s_axi_aclk);
   tick();s_axi_arvalid=0;while(!s_axi_rvalid)tick();
   saved=s_axi_rdata;saved_resp=s_axi_rresp;old_index=dut.output_index;
   repeat(turn%5)begin
    tick();if(!s_axi_rvalid||s_axi_rdata!==saved||s_axi_rresp!==saved_resp)$fatal(1,"R changed under stall");
    if(dut.output_index!==old_index)$fatal(1,"pixel popped before R handshake");
   end
   if(saved_resp!==response)$fatal(1,"read %h bad response",address);
   data=saved;s_axi_rready=1;tick();s_axi_rready=0;tick();turn=turn+1;transactions=transactions+1;
  end
 endtask
 task run_model(input string name,input integer frames);
  begin
   $readmemh({"../vectors/",name,"-config.hex"},config_words);
   $readmemh({"../vectors/",name,"-small-input.hex"},inputs);
   $readmemh({"../vectors/",name,"-small-output.hex"},golden);
   write_reg('h08,4,0);
   for(i=0;i<1776;i=i+1)begin
    write_reg('h20,i<1728?i:(i<1752?2048+i-1728:2080+i-1752),0);write_reg('h24,config_words[i],0);
   end
   write_reg('h08,8,0);read_reg('h0c,0,value);if(!value[3]||value[4])$fatal(1,"bad model status");
   write_reg('h08,1,0);
   for(i=0;i<35;i=i+1)write_reg('h10,inputs[i][23:0]^24'h808080,0);
   write_reg('h20,0,2);write_reg('h10,0,2);
   read_reg('h0c,0,value);while(!value[2])read_reg('h0c,0,value);
   for(i=0;i<35;i=i+1)begin
    read_reg('h18,0,value);if(value[23:0]!==(golden[i][23:0]^24'h808080))$fatal(1,"AXI %s pixel %d",name,i);
   end
   read_reg('h0c,0,value);if(value[0]||value[4]||!value[5])$fatal(1,"bad completed status");
   read_reg('h28,0,value);if(value!=963)$fatal(1,"bad compute cycle counter");
   read_reg('h2c,0,value);if(value!=frames)$fatal(1,"bad frame counter");
   read_reg('h30,0,value);if(value!=35)$fatal(1,"bad input count");
   read_reg('h34,0,value);if(value!=35)$fatal(1,"bad output count");
   read_reg('h18,2,value);
  end
 endtask
 initial begin
  repeat(5)tick();s_axi_aresetn=1;tick();
  read_reg(0,0,value);if(value!=32'h4e4e5332)$fatal(1,"bad capability");
  read_reg('h38,0,value);if(value!=963)$fatal(1,"bad compute profile");
  read_reg('h3c,0,value);if(value!=3)$fatal(1,"bad hardware capabilities");
  read_reg(4,0,value);if(value!={16'd5,16'd7})$fatal(1,"bad dimensions");
  write_reg(8,1,2);read_reg('h18,2,value);write_reg('hfffc,0,2);
  s_axi_wstrb=1;write_reg('h08,2,2);s_axi_wstrb=15;
  run_model("oil",1);run_model("anime",2);
  write_reg(8,2,0);read_reg('h0c,0,value);if(value[3]||value[0])$fatal(1,"soft reset did not discard model");
  $display("PASS CNN AXI separated AW/W, B/R stalls, pixel retirement, two trained models, invalid access and soft reset transactions=%0d",transactions);
  $finish;
 end
endmodule
