`timescale 1ns/1ps
module tb_java_cnn_unavailable;
 reg clk=0;always #5 clk=~clk;
 reg rstn=0;reg[15:0] awaddr=0,araddr=0;reg awvalid=0,wvalid=0,bready=0,arvalid=0,rready=0;
 wire awready,wready,bvalid,arready,rvalid;wire[1:0] bresp,rresp;wire[31:0] rdata;
 rix_java_cnn_unavailable dut(.s_axi_aclk(clk),.s_axi_aresetn(rstn),
 .s_axi_awaddr(awaddr),.s_axi_awprot(3'd0),.s_axi_awvalid(awvalid),.s_axi_awready(awready),
 .s_axi_wdata(32'hdeadbeef),.s_axi_wstrb(4'hf),.s_axi_wvalid(wvalid),.s_axi_wready(wready),
 .s_axi_bresp(bresp),.s_axi_bvalid(bvalid),.s_axi_bready(bready),
 .s_axi_araddr(araddr),.s_axi_arprot(3'd0),.s_axi_arvalid(arvalid),.s_axi_arready(arready),
 .s_axi_rdata(rdata),.s_axi_rresp(rresp),.s_axi_rvalid(rvalid),.s_axi_rready(rready));
 task tick;begin @(posedge clk);#1;end endtask
 task read_reg(input[15:0] addr,input[31:0] expected);
  begin @(negedge clk);araddr=addr;arvalid=1;tick();@(negedge clk);arvalid=0;
   repeat(4) begin tick();if(!rvalid||rdata!==expected||rresp!==0||arready) $fatal(1,"Read/stall identity failure");end
   @(negedge clk);rready=1;tick();@(negedge clk);rready=0;tick();if(rvalid)$fatal(1,"Read response not retired");
  end
 endtask
 task write_rejected(input integer address_first);
  begin
   @(negedge clk);if(address_first)awvalid=1;else wvalid=1;tick();
   @(negedge clk);awvalid=0;wvalid=0;repeat(3)tick();if(bvalid)$fatal(1,"Premature write response");
   @(negedge clk);if(address_first)wvalid=1;else awvalid=1;tick();@(negedge clk);awvalid=0;wvalid=0;tick();
   repeat(4)begin tick();if(!bvalid||bresp!==2'b10||awready||wready)$fatal(1,"Write not rejected/stable");end
   @(negedge clk);bready=1;tick();@(negedge clk);bready=0;tick();if(bvalid)$fatal(1,"Write response not retired");
  end
 endtask
 initial begin
  repeat(4)tick();@(negedge clk);rstn=1;
  read_reg(0,32'h4e4e5332);read_reg(4,0);read_reg(16'h3c,0);read_reg(16'h44,0);read_reg(16'h48,32'h4a415630);
  write_rejected(1);write_rejected(0);
  @(negedge clk);awvalid=1;tick();@(negedge clk);awvalid=0;rstn=0;tick();@(negedge clk);rstn=1;tick();
  if(bvalid||!awready||!wready)$fatal(1,"Reset did not clear partial transaction");
  $display("PASS JAVA_CNN_UNAVAILABLE reads=5 write_orders=2 stalled_responses=1 reset_partial=1 capabilities=0");$finish;
 end
 initial begin #100000;$fatal(1,"Timeout");end
endmodule
