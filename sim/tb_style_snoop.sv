`timescale 1ns/1ps
module tb_style_snoop;
 reg pixel_clk=0,gpu_clk=0,rst=1;always #5 pixel_clk=~pixel_clk;always #3 gpu_clk=~gpu_clk;
 reg [31:0] config_word=0;reg [11:0] x=0,y=0;reg hs=0,vs=0,de=0;reg [23:0] rgb=0;
 wire out_hs,out_vs,out_de;wire [23:0] out_rgb;
 rix_style_pixel style(.clk(pixel_clk),.*);
 reg request=0;reg [12:0] address=0;wire [15:0] data;wire acknowledged;
 rix_post_snoop snoop(.pixel_clk(pixel_clk),.pixel_rst(rst),.gpu_clk(gpu_clk),.gpu_rst(rst),.x(x),.y(y),.de(de),.rgb(rgb),.request(request),.address(address),.data(data),.acknowledged(acknowledged));
 task pixel(input [31:0] c,input [11:0] yy,input [23:0] p,input [23:0] expected);
 begin @(negedge pixel_clk);config_word=c;y=yy;rgb=p;de=1;@(posedge pixel_clk);#1;if(!out_de||out_rgb!==expected)$fatal(1,"style c=%h p=%h expected=%h got=%h",c,p,expected,out_rgb);end endtask
 task frame(input [7:0] blue);
 begin for(integer yy=0;yy<480;yy++)for(integer xx=0;xx<800;xx++)begin
 @(negedge pixel_clk);x=xx;y=yy;de=1;rgb={8'(xx),8'(yy),blue};
 end @(negedge pixel_clk);de=0;repeat(8)@(posedge gpu_clk);end endtask
 task read_sample(input integer index,input [7:0] blue);
 reg [23:0] p;reg [15:0] expected;begin
 @(negedge gpu_clk);address=index;repeat(3)@(posedge gpu_clk);#1;
 p={8'((index%100)*8),8'((index/100)*8),blue};expected={p[23:19],p[15:10],p[7:3]};
 if(data!==expected)$fatal(1,"capture %d expected=%h got=%h",index,expected,data);
 end endtask
 initial begin
 repeat(6)@(posedge pixel_clk);@(negedge pixel_clk);rst=0;
 pixel(0,0,24'hffffff,24'hffffff);pixel(16,0,24'h123456,24'h002449);
 pixel(32,0,24'hffffff,24'hffbe7f);pixel(48,0,24'hffffff,24'hffffff);pixel(48,0,24'h000000,0);
 pixel(16|256,432,24'h123456,24'h123456);pixel(16|256,431,24'h123456,24'h002449);
 @(negedge pixel_clk);de=0;request=1;repeat(8)@(posedge pixel_clk);
 frame(8'h5a);if(acknowledged!==1)$fatal(1,"capture did not acknowledge");
 for(integer i=0;i<6000;i+=137)read_sample(i,8'h5a);read_sample(5999,8'h5a);
 frame(8'hff);read_sample(0,8'h5a);read_sample(5999,8'h5a);
 @(negedge pixel_clk);request=0;repeat(8)@(posedge pixel_clk);frame(8'ha5);
 if(acknowledged!==0)$fatal(1,"second request did not acknowledge");read_sample(0,8'ha5);read_sample(5999,8'ha5);
 $display("PASS style colors, HUD boundary, full LCD capture, freeze and second capture");$finish;
 end
 initial begin #20000000;$fatal(1,"timeout");end
endmodule
