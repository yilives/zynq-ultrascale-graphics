// SPDX-License-Identifier: GPL-3.0-or-later
// Deterministic color styling, no neural-network or depth claims.
module rix_style_pixel(
 input wire clk,rst,input wire [31:0] config_word,
 input wire [11:0] y,input wire hs,vs,de,input wire [23:0] rgb,
 output reg out_hs,out_vs,out_de,output reg [23:0] out_rgb
);
 wire [7:0] r=rgb[23:16],g=rgb[15:8],b=rgb[7:0];
 wire [9:0] luminance=(r+{1'b0,g,1'b0}+b)>>2;
 wire preserve=config_word[8]&&y>=432;
 function [7:0] poster;input [7:0] v;begin poster={v[7:5],v[7:5],v[7:6]};end endfunction
 always @(posedge clk) begin
  if(rst) begin out_hs<=0;out_vs<=0;out_de<=0;out_rgb<=0;end
  else begin
   out_hs<=hs;out_vs<=vs;out_de<=de;out_rgb<=de?rgb:24'b0;
   if(de&&!preserve) case(config_word[5:4])
    1:out_rgb<={poster(r),poster(g),poster(b)};
    2:out_rgb<={luminance[7:0],(luminance[7:0]>>1)+(luminance[7:0]>>2),luminance[7:0]>>1};
    3:out_rgb<={3{luminance[7]?8'hff:8'h00}};
    default:out_rgb<=rgb;
   endcase
  end
 end
endmodule
