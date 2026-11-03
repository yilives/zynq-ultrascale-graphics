`timescale 1ns/1ps
// Full native timing, the real four-pixels/beat serializer, delayed AXI RAM.
module tb_neural_scanout #(parameter READER_BURST=256);
 reg clk=0;always #5 clk=~clk;
 reg rst=1,prepare=0;reg [11:0] x=0,y=0;reg de=0;
 wire idle,done,aborted,error,valid,ready;wire [127:0] data;
 wire [31:0] araddr;wire [7:0] arlen;wire [2:0] arsize;wire [1:0] arburst;
 wire arvalid,rready;reg arready=1,rvalid=0,rlast=0;reg [127:0] rdata=0;
 reg [1:0] lane=0;wire pixel_ready,dropped,out_hs,out_vs,out_de;
 wire [23:0] out_rgb;wire [31:0] underflow_count;
 integer left=0,latency=0,beat_index=0,gap=0,cycles=0,checked=0;
 integer xx,yy,frame,j;reg [31:0] lfsr=32'h12345678;
 function [23:0] color(input integer px,py);
  color={8'(px*17+py*3),8'(px*5+py*11),8'(px*7+py*9)};
 endfunction
 localparam W=400,H=240;
 function [23:0] golden(input integer ox,oy);
  integer ax,ay,bx,by,u,v,c,res;reg [23:0] a,b,cc,d;
  begin
   if(1==0) golden=color(ox,oy);
   else if(1==0) golden=color(ox/2,oy/2);
   else if(1==1) begin
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
 rix_frame_reader_dynamic #(.MAX_BURST_BEATS(READER_BURST)) reader(
  .clk(clk),.rst(rst),.start(prepare),.abort(dropped&&!prepare),
  .frame_base(32'h21000000),.frame_pixels(20'd15360),.idle(idle),.done(done),.aborted(aborted),.error(error),
  .data(data),.valid(valid),.ready(ready),.m_axi_araddr(araddr),.m_axi_arlen(arlen),.m_axi_arsize(arsize),.m_axi_arburst(arburst),
  .m_axi_arvalid(arvalid),.m_axi_arready(arready),.m_axi_rdata(rdata),.m_axi_rresp(2'b0),.m_axi_rlast(rlast),.m_axi_rvalid(rvalid),.m_axi_rready(rready));
 assign ready=pixel_ready&&lane==3;
 rix_scaler scale(.clk(clk),.rst(rst),.prepare(prepare),.mode(2'd3),
  .in_rgb(24'(data>>(lane*32))),.in_valid(valid),.in_ready(pixel_ready),.x(x),.y(y),.hs(1'b0),.vs(1'b0),.de(de),
  .out_hs(out_hs),.out_vs(out_vs),.out_de(out_de),.out_rgb(out_rgb),.dropped(dropped),.underflow_count(underflow_count));
 always @(posedge clk) begin
  if(rst||prepare)lane<=0;else if(valid&&pixel_ready)lane<=lane+1;
  if(!rst) begin
   if(rvalid&&!rready)$fatal(1,"Neural display held the shared DDR response channel");
   cycles<=cycles+1;lfsr<={lfsr[30:0],lfsr[31]^lfsr[21]^lfsr[1]^lfsr[0]};
   if(arvalid&&arready) begin
    if(left!=0||rvalid||arsize!=4||arburst!=1||((araddr&4095)+(arlen+1)*16)>4096)$fatal(1,"invalid AXI request");
    left<=arlen+1;latency<=40;beat_index<=(araddr-32'h21000000)/16;arready<=0;
   end
   if(latency>0)latency<=latency-1;
   if(gap>0)gap<=gap-1;
   if(left>0&&!rvalid&&latency==0&&gap==0)begin
    for(integer k=0;k<4;k=k+1)rdata[k*32+:32]<={8'b0,color((beat_index*4+k)%160,(beat_index*4+k)/160)};
    rvalid<=1;rlast<=left==1;
   end
   if(rvalid&&rready)begin
    left<=left-1;beat_index<=beat_index+1;
    if(left==1)begin rvalid<=0;arready<=1;end
    else if(lfsr[4:0]==0)begin rvalid<=0;gap<=lfsr[6:5];end
    else begin
     // A normal AXI RAM replaces a consumed beat without a mandatory bubble.
     for(integer k=0;k<4;k=k+1)rdata[k*32+:32]<={8'b0,color(((beat_index+1)*4+k)%160,((beat_index+1)*4+k)/160)};
     rlast<=left==2;
    end
   end
   if(error)$fatal(1,"AXI reader error");
  end
 end
 initial begin
  repeat(5)@(negedge clk);rst=0;
  for(frame=0;frame<2;frame=frame+1)begin
   wait(idle);@(negedge clk);prepare=1;de=0;
   @(negedge clk);prepare=0;
   repeat(29*1056)@(negedge clk);
   for(yy=0;yy<480;yy=yy+1)begin
    for(xx=0;xx<1056;xx=xx+1)begin
     @(negedge clk);x=xx;y=yy;de=xx<800;
     @(posedge clk);#1;
     if(de)begin
      if(dropped||!out_de||out_rgb!==golden(xx,yy))$fatal(1,"native xy=%0d,%0d frame=%0d got=%h expected=%h drop=%b burst=%0d",xx,yy,frame,out_rgb,golden(xx,yy),dropped,READER_BURST);
      checked=checked+1;
     end
    end
   end
   @(negedge clk);de=0;repeat(16*1056)@(negedge clk);
   if(underflow_count!=0)$fatal(1,"native underrun");
  end
  $display("PASS neural5x full 160x96 -> 800x480 scanout, 40-cycle AXI latency, random beat gaps, serializer, two frames %0d pixels",checked);$finish;
 end
 initial begin #20000000;$fatal(1,"native timeout");end
endmodule

