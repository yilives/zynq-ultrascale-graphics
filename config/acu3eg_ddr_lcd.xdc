# Generated LCD subset; DDR IP owns the 200 MHz input clock.
# Backlight PWM
set_property PACKAGE_PIN C11 [get_ports lcd_bl_pwm]
set_property IOSTANDARD LVCMOS33 [get_ports lcd_bl_pwm]

# Timing
set_property PACKAGE_PIN C12 [get_ports lcd_hsync]
set_property PACKAGE_PIN D12 [get_ports lcd_vsync]
set_property PACKAGE_PIN A11 [get_ports lcd_dclk]
set_property PACKAGE_PIN A12 [get_ports lcd_de]
set_property IOSTANDARD LVCMOS33 [get_ports {lcd_hsync lcd_vsync lcd_dclk lcd_de}]

# Blue
set_property PACKAGE_PIN F11 [get_ports {lcd_b[6]}]
set_property PACKAGE_PIN F12 [get_ports {lcd_b[7]}]
set_property PACKAGE_PIN E13 [get_ports {lcd_b[4]}]
set_property PACKAGE_PIN E14 [get_ports {lcd_b[5]}]
set_property PACKAGE_PIN A13 [get_ports {lcd_b[2]}]
set_property PACKAGE_PIN B13 [get_ports {lcd_b[3]}]
set_property PACKAGE_PIN A14 [get_ports {lcd_b[0]}]
set_property PACKAGE_PIN B14 [get_ports {lcd_b[1]}]
# Green
set_property PACKAGE_PIN C13 [get_ports {lcd_g[6]}]
set_property PACKAGE_PIN C14 [get_ports {lcd_g[7]}]
set_property PACKAGE_PIN L13 [get_ports {lcd_g[4]}]
set_property PACKAGE_PIN L14 [get_ports {lcd_g[5]}]
set_property PACKAGE_PIN H12 [get_ports {lcd_g[2]}]
set_property PACKAGE_PIN J12 [get_ports {lcd_g[3]}]
set_property PACKAGE_PIN J14 [get_ports {lcd_g[0]}]
set_property PACKAGE_PIN K14 [get_ports {lcd_g[1]}]
# Red
set_property PACKAGE_PIN H13 [get_ports {lcd_r[6]}]
set_property PACKAGE_PIN H14 [get_ports {lcd_r[7]}]
set_property PACKAGE_PIN F13 [get_ports {lcd_r[4]}]
set_property PACKAGE_PIN G13 [get_ports {lcd_r[5]}]
set_property PACKAGE_PIN G14 [get_ports {lcd_r[2]}]
set_property PACKAGE_PIN G15 [get_ports {lcd_r[3]}]
set_property PACKAGE_PIN D14 [get_ports {lcd_r[0]}]
set_property PACKAGE_PIN D15 [get_ports {lcd_r[1]}]

set_property IOSTANDARD LVCMOS33 [get_ports {lcd_r[*] lcd_g[*] lcd_b[*]}]

# ----------------------------------------------------------------------------
# GT911 touch (J45) — from AN970 pin map / board expansion
# ----------------------------------------------------------------------------
set_property PACKAGE_PIN F10 [get_ports touch_scl]
set_property PACKAGE_PIN G11 [get_ports touch_sda]
set_property PACKAGE_PIN B10 [get_ports touch_int]
set_property IOSTANDARD LVCMOS33 [get_ports {touch_scl touch_sda touch_int}]

# Async inputs
set_false_path -from [get_ports touch_int]
set_false_path -to [get_ports lcd_bl_pwm]

# DDR RESET_n is an asynchronous controller init output, not a synchronous data path.
set_false_path -to [get_ports ddr4_reset_n]

# Forwarded rising DCLK occurs half a cycle after RGB/control updates.
create_generated_clock -name lcd_forwarded -source [get_pins lcd_clock/C] -divide_by 1 -invert [get_ports lcd_dclk]
# Provisional interface budget: 5 ns setup and 2 ns hold, including board skew.
# Must still be checked against the physical panel/cable on board.
set_output_delay -clock lcd_forwarded -max 5.000 [get_ports {lcd_r[*] lcd_g[*] lcd_b[*] lcd_de lcd_hsync lcd_vsync}]
set_output_delay -clock lcd_forwarded -min -2.000 [get_ports {lcd_r[*] lcd_g[*] lcd_b[*] lcd_de lcd_hsync lcd_vsync}]
