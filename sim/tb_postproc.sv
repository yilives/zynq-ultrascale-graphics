`timescale 1ns/1ps
module tb_postproc;
 localparam W=10,H=15;
 reg clk=0,rst=1,prepare=0;always #5 clk=~clk;
 reg [1:0] mode=0;reg [23:0] in_rgb=0;reg in_valid=0;
 wire in_ready;reg [11:0] x=0,y=0;reg hs=0,vs=0,de=0;
 wire out_hs,out_vs,out_de,dropped;wire [23:0] out_rgb;wire [31:0] underflow_count;
 rix_scaler #(.WIDTH(W),.HEIGHT(H)) dut(.*);
 integer ix=0,iy=0,seed=17,iw,ih,m,xx,yy,k,seen=0;
 reg feeding=0;
 function [23:0] color(input integer px,py);
  begin color={8'(px*17+py*3),8'(px*5+py*11),8'(px*7+py*9)};end
 endfunction
 function [23:0] golden(input integer ox,oy,mm);
  integer ax,ay,bx,by,u,v,c,res;reg [23:0] a,b,cc,d;
  begin
   if(mm==2) golden=color(ox,oy);
   else if(mm==0) golden=color(ox/2,oy/2);
   else if(mm==3) begin
    ax=ox<2?0:(ox-2)/5;ay=oy<2?0:(oy-2)/5;
    bx=ax+1<2*W/5?ax+1:ax;by=ay+1<2*H/5?ay+1:ay;
    u=ox<2?0:(ox-2)%5;v=oy<2?0:(oy-2)%5;
    a=color(ax,ay);b=color(bx,ay);cc=color(ax,by);d=color(bx,by);
    for(c=0;c<3;c=c+1) begin
     res=(a[c*8+:8]*(5-u)*(5-v)+b[c*8+:8]*u*(5-v)+cc[c*8+:8]*(5-u)*v+d[c*8+:8]*u*v+12)/25;
     golden[c*8+:8]=res;
    end
   end else begin
    ax=ox==0?0:(ox-1)/2;ay=oy==0?0:(oy-1)/2;
    bx=ox==0?0:(ax+1<W?ax+1:ax);by=oy==0?0:(ay+1<H?ay+1:ay);
    u=ox==0?0:(ox%2?1:3);v=oy==0?0:(oy%2?1:3);
    a=color(ax,ay);b=color(bx,ay);cc=color(ax,by);d=color(bx,by);
    for(c=0;c<3;c=c+1) begin
     res=(a[c*8+:8]*(4-u)*(4-v)+b[c*8+:8]*u*(4-v)+cc[c*8+:8]*(4-u)*v+d[c*8+:8]*u*v+8)/16;
     golden[c*8+:8]=res;
    end
   end
  end
 endfunction
 always @(posedge clk) if(!rst&&feeding&&in_valid&&in_ready) begin
  if(ix==iw-1) begin ix=0;iy=iy+1;end else ix=ix+1;
 end
 always @(negedge clk) begin
  seed=(seed*1103515245+12345)&32'h7fffffff;
  in_valid=feeding&&iy<ih&&(seed%4!=0);
  in_rgb=color(ix,iy);
 end
 initial begin
  repeat(5) @(negedge clk);rst=0;
  for(m=0;m<4;m=m+1) begin
   @(negedge clk);mode=m;prepare=1;feeding=0;ix=0;iy=0;de=0;
   iw=m==2?2*W:(m==3?2*W/5:W);ih=m==2?2*H:(m==3?2*H/5:H);
   @(negedge clk);prepare=0;feeding=1;
   repeat(160) @(negedge clk);
   for(yy=0;yy<2*H;yy=yy+1) begin
    for(xx=0;xx<2*W;xx=xx+1) begin
     @(negedge clk);x=xx;y=yy;de=1;
     @(posedge clk);#1;
     if(dropped||!out_de||out_rgb!==golden(xx,yy,m))
      $fatal(1,"scaler mode=%0d xy=%0d,%0d got=%h expected=%h dropped=%b",m,xx,yy,out_rgb,golden(xx,yy,m),dropped);
     seen=seen+1;
    end
    @(negedge clk);de=0;repeat(16) @(negedge clk);
   end
   @(negedge clk);feeding=0;de=0;
   if(underflow_count!=0) $fatal(1,"Unexpected underflow");
  end
  $display("PASS: POSTPROC nearest/bilinear/native boundaries, random input gaps and row reuse %0d pixels",seen);$finish;
 end
 initial begin #1000000;$fatal(1,"timeout");end
endmodule
