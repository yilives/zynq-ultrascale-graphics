# Only asynchronous assertion pins of the board reset synchronizer chains.
# Output recovery uses four local stages plus a final registered reset source.
# Data/handshake crossings remain constrained in rasterix_cdc.xdc.
set reset_sync [get_cells -hier -regexp {.*(base_pipe|mig_pipe|pixel_pipe)_reg\[[0-3]\]}]
set_false_path -to [get_pins -of_objects $reset_sync -filter {REF_PIN_NAME == CLR}]
