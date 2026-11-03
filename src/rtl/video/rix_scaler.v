// SPDX-License-Identifier: GPL-3.0-or-later
// Four tagged rows: LR 2x, native HR, or neural RGB 160x96 -> 800x480 5x.
module rix_scaler #(parameter WIDTH=400,HEIGHT=240)(
 input wire clk,rst,prepare,input wire [1:0] mode,
 input wire [23:0] in_rgb,input wire in_valid,output wire in_ready,
 input wire [11:0] x,y,input wire hs,vs,de,
 output reg out_hs,out_vs,out_de,output reg [23:0] out_rgb,
 output reg dropped,output reg [31:0] underflow_count
);
 // Small distributed multi-read window; explicitly budgeted in utilization.
 (* ram_style="distributed" *) reg [23:0] rows[0:8*WIDTH-1];
 reg [3:0] ready_rows;
 reg [11:0] tags[0:3];
 reg [11:0] in_x,in_y;
 wire native=mode==2;
 wire bilinear=mode==1;
 wire neural=mode==3;
 wire [11:0] iw=native?2*WIDTH:(neural?(2*WIDTH)/5:WIDTH), ih=native?2*HEIGHT:(neural?(2*HEIGHT)/5:HEIGHT);
 wire [11:0] px5=x<2?0:x-2,py5=y<2?0:y-2;
 wire [2:0] fx5=px5%5,fy5=py5%5;
 wire [11:0] sx=native?x:(neural?px5/5:(bilinear?(x==0?0:(x-1)>>1):x>>1));
 wire [11:0] sy=native?y:(neural?py5/5:(bilinear?(y==0?0:(y-1)>>1):y>>1));
 wire [11:0] nx=sx+1<iw?sx+1:sx,ny=sy+1<ih?sy+1:sy;
 wire [1:0] fx=x==0?0:(x[0]?1:3), fy=y==0?0:(y[0]?1:3);
 wire available=ready_rows[sy[1:0]]&&tags[sy[1:0]]==sy &&
  (!(bilinear||neural)||(ready_rows[ny[1:0]]&&tags[ny[1:0]]==ny));
 assign in_ready=!prepare&&!dropped&&in_y<ih&&!ready_rows[in_y[1:0]];
 function [7:0] mix;
  input [7:0] a,b,c,d;input [1:0] u,v;
  reg [15:0] value;
  begin value=a*(4-u)*(4-v)+b*u*(4-v)+c*(4-u)*v+d*u*v+8;mix=value>>4;end
 endfunction
 function [7:0] mix5;
  input [7:0] a,b,c,d;input [2:0] u,v;
  reg [10:0] top,bottom;reg [12:0] total;
  begin
   top=a*(3'd5-u)+b*u;bottom=c*(3'd5-u)+d*u;
   total=top*(3'd5-v)+bottom*v+13'd12;
   mix5=total/13'd25;
  end
 endfunction
 wire [23:0] a=rows[sy[1:0]*2*WIDTH+sx];
 wire [23:0] b=rows[sy[1:0]*2*WIDTH+nx];
 wire [23:0] c=rows[ny[1:0]*2*WIDTH+sx];
 wire [23:0] d=rows[ny[1:0]*2*WIDTH+nx];
 integer i;
 always @(posedge clk) begin
  if(rst) begin
   ready_rows<=0;in_x<=0;in_y<=0;dropped<=1;underflow_count<=0;
   out_hs<=0;out_vs<=0;out_de<=0;out_rgb<=0;
   for(i=0;i<4;i=i+1) tags[i]<=0;
  end else begin
   out_hs<=hs;out_vs<=vs;out_de<=de;out_rgb<=0;
   if(prepare) begin ready_rows<=0;in_x<=0;in_y<=0;dropped<=0;end
   else begin
    if(in_valid&&in_ready) begin
     rows[in_y[1:0]*2*WIDTH+in_x]<=in_rgb;
     if(in_x==iw-1) begin
      ready_rows[in_y[1:0]]<=1;tags[in_y[1:0]]<=in_y;in_x<=0;in_y<=in_y+1;
     end else in_x<=in_x+1;
    end
    if(de&&!dropped&&x<2*WIDTH&&y<2*HEIGHT) begin
     if(!available) begin dropped<=1;underflow_count<=underflow_count+1;end
     else if(neural) out_rgb<={mix5(a[23:16],b[23:16],c[23:16],d[23:16],fx5,fy5),
      mix5(a[15:8],b[15:8],c[15:8],d[15:8],fx5,fy5),mix5(a[7:0],b[7:0],c[7:0],d[7:0],fx5,fy5)};
     else if(bilinear) out_rgb<={mix(a[23:16],b[23:16],c[23:16],d[23:16],fx,fy),
      mix(a[15:8],b[15:8],c[15:8],d[15:8],fx,fy),mix(a[7:0],b[7:0],c[7:0],d[7:0],fx,fy)};
     else out_rgb<=a;
     if(x==2*WIDTH-1) begin
      if(native) ready_rows[y[1:0]]<=0;
      else if(neural) begin
       if(y>=2&&fy5==4) ready_rows[sy[1:0]]<=0;
      end
      else if(bilinear) begin
       if(y>=2&&!y[0]) ready_rows[((y>>1)-1)&3]<=0;
      end else if(y[0]) ready_rows[(y>>1)&3]<=0;
     end
    end
   end
  end
 end
endmodule
