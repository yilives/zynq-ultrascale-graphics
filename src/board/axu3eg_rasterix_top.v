// SPDX-License-Identifier: GPL-3.0-or-later
module axu3eg_rasterix_top(
 input wire pl_clk0_p,pl_clk0_n,sys_rst_n,
 output wire led,lcd_dclk,lcd_hsync,lcd_vsync,lcd_de,lcd_bl_pwm,
 output wire [7:0] lcd_r,lcd_g,lcd_b,
 inout wire touch_scl,touch_sda,input wire touch_int,
 output wire [16:0] ddr4_adr,output wire [1:0] ddr4_ba,
 output wire [0:0] ddr4_bg,ddr4_cke,ddr4_cs_n,ddr4_odt,ddr4_ck_t,ddr4_ck_c,
 output wire ddr4_act_n,ddr4_reset_n,
 inout wire [15:0] ddr4_dq,inout wire [1:0] ddr4_dqs_t,ddr4_dqs_c,ddr4_dm_dbi_n
);
 wire pixel_clk,fault;wire [23:0] rgb;
 rasterix_system_wrapper system_i(
 .pl_clock_clk_p(pl_clk0_p),.pl_clock_clk_n(pl_clk0_n),.reset_n(sys_rst_n),
 .DDR4_adr(ddr4_adr),.DDR4_ba(ddr4_ba),.DDR4_bg(ddr4_bg),
 .DDR4_cke(ddr4_cke),.DDR4_cs_n(ddr4_cs_n),.DDR4_odt(ddr4_odt),
 .DDR4_ck_t(ddr4_ck_t),.DDR4_ck_c(ddr4_ck_c),.DDR4_act_n(ddr4_act_n),
 .DDR4_reset_n(ddr4_reset_n),.DDR4_dq(ddr4_dq),.DDR4_dqs_t(ddr4_dqs_t),
 .DDR4_dqs_c(ddr4_dqs_c),.DDR4_dm_n(ddr4_dm_dbi_n),
 .pixel_clk(pixel_clk),.lcd_hs(lcd_hsync),.lcd_vs(lcd_vsync),.lcd_de(lcd_de),.lcd_rgb(rgb),.fault(fault));
 assign {lcd_r,lcd_g,lcd_b}=rgb;
 ODDRE1 #(.IS_C_INVERTED(0),.IS_D1_INVERTED(0),.IS_D2_INVERTED(0),.SRVAL(0))
 lcd_clock(.C(pixel_clk),.D1(1'b0),.D2(1'b1),.SR(1'b0),.Q(lcd_dclk));
 assign lcd_bl_pwm=1'b1,led=!fault,touch_scl=1'bz,touch_sda=1'bz;
endmodule
