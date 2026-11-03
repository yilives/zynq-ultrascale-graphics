// SPDX-License-Identifier: GPL-3.0-or-later
// Frozen 100x60 RGB565 thumbnail of actual postprocessed LCD pixels.
module rix_post_snoop(
 input wire pixel_clk,pixel_rst,input wire [11:0] x,y,input wire de,input wire [23:0] rgb,
 input wire gpu_clk,gpu_rst,input wire request,input wire [12:0] address,
 output reg [15:0] data,output wire acknowledged
);
 (* ram_style="block" *) reg [15:0] memory[0:5999];
 (* ASYNC_REG="TRUE" *) reg [2:0] req_sync,ack_sync;
 reg ack,active;
 wire start=req_sync[2]!=ack&&!active&&de&&x==0&&y==0;
 wire sample=(active||start)&&de&&x[2:0]==0&&y[2:0]==0&&x<800&&y<480;
 assign acknowledged=ack_sync[2];
 always @(posedge gpu_clk) begin
  if(gpu_rst) begin ack_sync<=0;data<=0;end
  else begin ack_sync<={ack_sync[1:0],ack};if(address<6000)data<=memory[address];else data<=0;end
 end
 always @(posedge pixel_clk) begin
  if(pixel_rst) begin req_sync<=0;ack<=0;active<=0;end
  else begin
   req_sync<={req_sync[1:0],request};
   if(start) active<=1;
   if(sample) begin
    memory[(y>>3)*100+(x>>3)]<={rgb[23:19],rgb[15:10],rgb[7:3]};
    if(x==792&&y==472) begin active<=0;ack<=req_sync[2];end
   end
  end
 end
endmodule
