// AN970 800x480 DE-mode timing
// Horizontal total 1056 (800 active + 256 blank)
// Vertical   total 525  (480 active + 45 blank)
// DCLK = 1056*525*60 = 33.264 MHz
`timescale 1ns / 1ps
module video_timing #(
    parameter H_ACTIVE = 800,
    parameter H_FP     = 40,
    parameter H_SYNC   = 48,
    parameter H_BP     = 168, // 40+48+168=256
    parameter V_ACTIVE = 480,
    parameter V_FP     = 13,
    parameter V_SYNC   = 3,
    parameter V_BP     = 29   // 13+3+29=45
) (
    input  wire       clk,      // pixel clock
    input  wire       rst,
    output reg  [11:0] x,       // 0..H_ACTIVE-1 when de
    output reg  [11:0] y,
    output reg        hs,
    output reg        vs,
    output reg        de,
    output reg        frame_start
);
    localparam H_TOTAL = H_ACTIVE + H_FP + H_SYNC + H_BP;
    localparam V_TOTAL = V_ACTIVE + V_FP + V_SYNC + V_BP;

    reg [11:0] h_cnt;
    reg [11:0] v_cnt;

    always @(posedge clk) begin
        if (rst) begin
            h_cnt <= 12'd0;
            v_cnt <= 12'd0;
            hs <= 1'b0;
            vs <= 1'b0;
            de <= 1'b0;
            x <= 12'd0;
            y <= 12'd0;
            frame_start <= 1'b0;
        end else begin
            frame_start <= 1'b0;
            if (h_cnt == H_TOTAL - 1) begin
                h_cnt <= 12'd0;
                if (v_cnt == V_TOTAL - 1) begin
                    v_cnt <= 12'd0;
                    frame_start <= 1'b1;
                end else begin
                    v_cnt <= v_cnt + 12'd1;
                end
            end else begin
                h_cnt <= h_cnt + 12'd1;
            end

            // DE: active window
            de <= (h_cnt < H_ACTIVE) && (v_cnt < V_ACTIVE);
            x  <= (h_cnt < H_ACTIVE) ? h_cnt : 12'd0;
            y  <= (v_cnt < V_ACTIVE) ? v_cnt : 12'd0;

            // positive sync pulses inside blanking
            hs <= (h_cnt >= H_ACTIVE + H_FP) && (h_cnt < H_ACTIVE + H_FP + H_SYNC);
            vs <= (v_cnt >= V_ACTIVE + V_FP) && (v_cnt < V_ACTIVE + V_FP + V_SYNC);
        end
    end
endmodule
