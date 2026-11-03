// SPDX-License-Identifier: GPL-3.0-or-later
// Two row banks. Each source pixel is read once, displayed in a 2x2 block.
// Sequential input must complete WIDTH pixels per row before that row is scanned.
module scale2x_nearest #(parameter WIDTH=400,HEIGHT=240)(
    input wire clk,rst,prepare,
    input wire [23:0] in_rgb,
    input wire in_valid,
    output wire in_ready,
    input wire [11:0] x,y,
    input wire hs,vs,de,
    output reg out_hs,out_vs,out_de,
    output reg [23:0] out_rgb,
    output reg dropped,
    output reg [31:0] underflow_count
);
    (* ram_style="block" *) reg [23:0] rows[0:2*WIDTH-1];
    reg [1:0] ready_rows;
    reg [11:0] tag0,tag1,in_x,in_y;
    wire bank=y[1];
    wire row_available=ready_rows[bank]&&((bank?tag1:tag0)==(y>>1));
    assign in_ready=!prepare&&!dropped&&in_y<HEIGHT&&!ready_rows[in_y[0]];
    always @(posedge clk) begin
        if(rst) begin
            ready_rows<=0;tag0<=0;tag1<=0;in_x<=0;in_y<=0;
            out_rgb<=0;out_hs<=0;out_vs<=0;out_de<=0;dropped<=1;underflow_count<=0;
        end else begin
            out_hs<=hs;out_vs<=vs;out_de<=de;out_rgb<=0;
            if(prepare) begin ready_rows<=0;in_x<=0;in_y<=0;dropped<=0;end
            else begin
                if(in_valid&&in_ready) begin
                    rows[in_y[0]*WIDTH+in_x]<=in_rgb;
                    if(in_x==WIDTH-1) begin
                        ready_rows[in_y[0]]<=1;
                        if(in_y[0]) tag1<=in_y;else tag0<=in_y;
                        in_x<=0;in_y<=in_y+1;
                    end else in_x<=in_x+1;
                end
                if(de&&!dropped&&x<2*WIDTH&&y<2*HEIGHT) begin
                    if(row_available) out_rgb<=rows[bank*WIDTH+(x>>1)];
                    else begin dropped<=1;underflow_count<=underflow_count+1;end
                    if(x==2*WIDTH-1&&y[0]) ready_rows[bank]<=0;
                end
            end
        end
    end
endmodule
