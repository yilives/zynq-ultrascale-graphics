# Bit-banged I2C is asynchronous to the AXI clock; no synchronous external timing.
set_false_path -from [get_ports {touch_scl touch_sda}]
set_false_path -to [get_ports {touch_scl touch_sda touch_int}]
