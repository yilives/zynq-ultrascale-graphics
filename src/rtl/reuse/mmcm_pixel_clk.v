// MMCME4 helper for AN970 pixel clock.
// Input: 200 MHz (pl_clk0). Output: ~33.333 MHz (or 33.264 if fine-tuned).
// 200 / 6 = 33.3333 MHz  (0.2% fast vs 33.264 — acceptable per plan)
// For exact 33.264: use CLKFBOUT_MULT_F / CLKOUT0_DIVIDE_F with fractional.
`timescale 1ns / 1ps
module mmcm_pixel_clk (
    input  wire clk_in_200,   // single-ended after IBUFDS outside, or use clk_in_200_p/n
    input  wire rst,
    output wire clk_pix,      // ~33.333 MHz
    output wire clk_pix_bufg,
    output wire locked
);
    wire clkfbout;
    wire clkfbout_buf;
    wire clkout0;

    MMCME4_BASE #(
        .BANDWIDTH          ("OPTIMIZED"),
        .CLKIN1_PERIOD      (5.000),      // 200 MHz
        .CLKFBOUT_MULT_F    (6.000),      // VCO = 1200
        .DIVCLK_DIVIDE      (1),
        .CLKOUT0_DIVIDE_F   (36.000),     // 1200/36 = 33.333 MHz
        .CLKOUT0_PHASE      (0.0),
        .CLKOUT0_DUTY_CYCLE (0.500),
        .STARTUP_WAIT       ("FALSE")
    ) mmcm_i (
        .CLKOUT0    (clkout0),
        .CLKOUT0B   (),
        .CLKOUT1    (),
        .CLKOUT1B   (),
        .CLKOUT2    (),
        .CLKOUT2B   (),
        .CLKOUT3    (),
        .CLKOUT3B   (),
        .CLKOUT4    (),
        .CLKOUT5    (),
        .CLKOUT6    (),
        .CLKFBOUT   (clkfbout),
        .CLKFBOUTB  (),
        .LOCKED     (locked),
        .CLKIN1     (clk_in_200),
        .PWRDWN     (1'b0),
        .RST        (rst),
        .CLKFBIN    (clkfbout_buf)
    );

    BUFG bufg_fb  (.I(clkfbout), .O(clkfbout_buf));
    BUFG bufg_pix (.I(clkout0),  .O(clk_pix_bufg));

    assign clk_pix = clkout0;
endmodule
