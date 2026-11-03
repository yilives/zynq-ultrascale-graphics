// SPDX-License-Identifier: GPL-3.0-or-later
// Expose the physical 200/6 MHz clock ratio to IP Integrator.
module rix_pixel_clock(
 (* X_INTERFACE_INFO="xilinx.com:signal:clock:1.0 input_clock CLK", X_INTERFACE_PARAMETER="FREQ_HZ 200000000" *) input wire input_clock,
 input wire rst,
 (* X_INTERFACE_INFO="xilinx.com:signal:clock:1.0 output_clock CLK", X_INTERFACE_PARAMETER="FREQ_HZ 33333333, CLK_DOMAIN rasterix_pixel" *) output wire output_clock,
 output wire locked
);
 mmcm_pixel_clk impl(.clk_in_200(input_clock),.rst(rst),.clk_pix(),.clk_pix_bufg(output_clock),.locked(locked));
endmodule
