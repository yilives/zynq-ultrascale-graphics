# ISOLATED ATOMIC V4; accepted base is read-only.
# Independent AXU3EG PS + DMA + GPU + PL DDR/LCD project.
# -tclargs candidate: validate connectivity with unverified PS base; no bit/XSA.
# -tclargs board: requires verified configuration before synthesis/export.
set root [file normalize [file join [file dirname [info script]] ..]]
source [file join $root generated rasterix_config.tcl]
set mode [lindex $argv 0]
if {$mode ni {candidate board}} {error "Use -tclargs candidate or board"}
if {$mode eq "board" && !$rix_board_verified} {error "Verify PS preset and reserved PS DDR base, then generate_config.py --board"}
set out [file join $root build vivado_java256_nofsr_r1]
if {[file exists [file join $out rix_java256_nofsr_r1.xpr]]} {error "Isolated project already exists; refuse implicit overwrite"}
create_project rix_java256_nofsr_r1 $out -part $rix_part
set_property ip_cache_permissions {read} [current_project]
set_property target_language Verilog [current_project]
update_ip_catalog
set rix [file join $root external RasterIX rtl]
foreach dir [list [file join $rix RasterIX] [file join $rix Float rtl float] [file join $rix 3rdParty verilog-axi] [file join $rix 3rdParty verilog-axis]] {add_files -norecurse [glob -directory $dir *.v]}
add_files -norecurse [list [file join $rix 3rdParty skidbuffer.v] [file join $rix 3rdParty sfifo.v] [file join $rix 3rdParty afifo.v]]

foreach dir {common gpu video top reuse} {add_files -norecurse [glob -directory [file join $root src rtl $dir] *.v]}
foreach name {rix_scaler.v rasterix_linux_top.v rix_frame_reader_dynamic.v} {
 set original [get_files -quiet */$name]
 if {[llength $original]!=1} {error "Expected exactly one shared video source: $name"}
 remove_files $original
 add_files -norecurse [file join $root build fsr-pl video-v24-burstcache video $name]
}
 
set_property include_dirs [list [file join $rix RasterIX]] [current_fileset]
set headers [glob -directory [file join $rix RasterIX] *.vh]
set headers [lsearch -all -inline -not -glob $headers */RasterizerCommands.vh]
add_files -norecurse $headers
set_property file_type {Verilog Header} [get_files *.vh]
set_property used_in_synthesis false [get_files *.vh]

add_files -norecurse [file join $root src rtl experiments rix_java_cnn_unavailable.sv]
foreach name {rasterix_linux_top.v rix_control.v TextureReader.v} {
 set originals [get_files -quiet */$name]
 if {[llength $originals]!=1} {error "Expected one private override source: $name"}
 remove_files $originals
 add_files -norecurse [file join $root build minecraft-java-125 no-fsr-base-r1 rtl $name]
}
create_bd_design rasterix_system

proc ip {name pattern} {
    set defs [get_ipdefs -all $pattern]
    if {![llength $defs]} {error "Missing IP $pattern"}
    return [create_bd_cell -type ip -vlnv [lindex $defs end] $name]
}
proc pins {args} {set p {};foreach a $args {lappend p [get_bd_pins $a]};connect_bd_net {*}$p}
proc bus {a b} {connect_bd_intf_net [get_bd_intf_pins $a] [get_bd_intf_pins $b]}
ip ps xilinx.com:ip:zynq_ultra_ps_e:*
source [file join $root $rix_ps_preset]
set_ps_config ps
set_property -dict [list CONFIG.PSU__USE__M_AXI_GP0 {1} CONFIG.PSU__USE__M_AXI_GP1 {0} CONFIG.PSU__USE__M_AXI_GP2 {0} CONFIG.PSU__USE__S_AXI_GP2 {1} \
    CONFIG.PSU__MAXIGP0__DATA_WIDTH {32} CONFIG.PSU__SAXIGP2__DATA_WIDTH {128} \
    CONFIG.PSU__FPGA_PL0_ENABLE {1} CONFIG.PSU__CRL_APB__PL0_REF_CTRL__FREQMHZ {100} \
    CONFIG.PSU__USE__IRQ0 {1}] [get_bd_cells ps]
ip axi_dma_0 xilinx.com:ip:axi_dma:*
set_property -dict [list CONFIG.c_include_sg {0} CONFIG.c_addr_width {32} \
    CONFIG.c_m_axi_mm2s_data_width {64} CONFIG.c_m_axi_s2mm_data_width {64} \
    CONFIG.c_m_axis_mm2s_tdata_width {32} CONFIG.c_s_axis_s2mm_tdata_width {32} \
    CONFIG.c_mm2s_burst_size {16} CONFIG.c_s2mm_burst_size {16} \
    CONFIG.c_sg_length_width {23} CONFIG.c_include_mm2s_dre {0} CONFIG.c_include_s2mm_dre {0}] [get_bd_cells axi_dma_0]
create_bd_cell -type module -reference rasterix_linux_top gpu
set_property CONFIG.PS_GFX_BASE $rix_ps_base [get_bd_cells gpu]
ip ps_memory xilinx.com:ip:smartconnect:*
set_property -dict [list CONFIG.NUM_SI {4} CONFIG.NUM_MI {1}] [get_bd_cells ps_memory]
bus gpu/M_GPU_AXI ps_memory/S00_AXI
bus gpu/M_PS_AXI ps_memory/S01_AXI
bus axi_dma_0/M_AXI_MM2S ps_memory/S02_AXI
bus axi_dma_0/M_AXI_S2MM ps_memory/S03_AXI
bus ps_memory/M00_AXI ps/S_AXI_HP0_FPD
bus axi_dma_0/M_AXIS_MM2S gpu/S_CMD_AXIS
bus gpu/M_RESP_AXIS axi_dma_0/S_AXIS_S2MM
ip control xilinx.com:ip:smartconnect:*
set_property -dict [list CONFIG.NUM_SI {1} CONFIG.NUM_MI {4} CONFIG.NUM_CLKS {1}] [get_bd_cells control]

# Keep the PS address aperture unchanged. A full AXI decoder separates memory
# before an explicit AXI4->Lite protocol boundary; no HPM1/DT relocation.
ip control_decode xilinx.com:ip:axi_crossbar:*
set_property -dict [list CONFIG.NUM_SI {1} CONFIG.NUM_MI {2}] [get_bd_cells control_decode]
ip control_protocol xilinx.com:ip:axi_protocol_converter:*
set_property -dict [list CONFIG.SI_PROTOCOL {AXI4} CONFIG.MI_PROTOCOL {AXI4LITE}] [get_bd_cells control_protocol]
bus ps/M_AXI_HPM0_FPD control_decode/S00_AXI
bus control_decode/M00_AXI control_protocol/S_AXI
bus control_protocol/M_AXI control/S00_AXI
create_bd_cell -type module -reference rix_java_cnn_unavailable neural

bus control/M03_AXI neural/s_axi


bus control/M00_AXI axi_dma_0/S_AXI_LITE
bus control/M01_AXI gpu/S_CONTROL_AXI
ip touch_gpio xilinx.com:ip:axi_gpio:*
set_property -dict [list CONFIG.C_GPIO_WIDTH {3} CONFIG.C_ALL_INPUTS {0} CONFIG.C_ALL_OUTPUTS {0} CONFIG.C_INTERRUPT_PRESENT {1} CONFIG.C_IS_DUAL {0} CONFIG.C_TRI_DEFAULT {0x00000007} CONFIG.C_DOUT_DEFAULT {0x00000000}] [get_bd_cells touch_gpio]
bus control/M02_AXI touch_gpio/S_AXI
make_bd_intf_pins_external [get_bd_intf_pins touch_gpio/GPIO]
set_property name touch_gpio [get_bd_intf_ports GPIO_0]
ip pl_ddr4 xilinx.com:ip:ddr4:*
set_property -dict [list CONFIG.C0.DDR4_isCustom {true} \
    CONFIG.C0.DDR4_CustomParts [file join $root config acu3eg_ddr4_1600.csv] \
    CONFIG.C0.DDR4_MemoryPart {CUSTOM_ACU3EG_MT40A512M16LY_062E_1600} \
    CONFIG.C0.DDR4_TimePeriod {1250} CONFIG.C0.DDR4_InputClockPeriod {5000} \
    CONFIG.C0.DDR4_DataWidth {16} CONFIG.C0.DDR4_DataMask {DM_NO_DBI} \
    CONFIG.C0.DDR4_AxiSelection {true} CONFIG.C0.DDR4_AxiDataWidth {128} \
    CONFIG.C0.DDR4_AxiIDWidth {4} CONFIG.System_Clock {Differential} \
    CONFIG.Debug_Signal {Disable}] [get_bd_cells pl_ddr4]
make_bd_intf_pins_external [get_bd_intf_pins pl_ddr4/C0_DDR4]
set_property name DDR4 [get_bd_intf_ports C0_DDR4_0]
make_bd_intf_pins_external [get_bd_intf_pins pl_ddr4/C0_SYS_CLK]
set_property name pl_clock [get_bd_intf_ports C0_SYS_CLK_0]
set_property CONFIG.FREQ_HZ 200000000 [get_bd_intf_ports pl_clock]
create_bd_cell -type module -reference rix_pixel_clock pixel_clock
pins pl_ddr4/c0_ddr4_ui_clk pixel_clock/input_clock
pins pl_ddr4/c0_ddr4_ui_clk_sync_rst pixel_clock/rst
pins pixel_clock/output_clock gpu/pixel_clk
ip pl_memory xilinx.com:ip:smartconnect:*
set_property -dict [list CONFIG.NUM_SI {3} CONFIG.NUM_MI {1} CONFIG.NUM_CLKS {3}] [get_bd_cells pl_memory]
bus gpu/M_PL_WRITE_AXI pl_memory/S00_AXI
bus gpu/M_SCAN_AXI pl_memory/S01_AXI

bus control_decode/M01_AXI pl_memory/S02_AXI

bus pl_memory/M00_AXI pl_ddr4/C0_DDR4_S_AXI
pins ps/pl_clk0 gpu/gpu_clk ps_memory/aclk control/aclk pl_memory/aclk \
    ps/maxihpm0_fpd_aclk ps/saxihp0_fpd_aclk axi_dma_0/s_axi_lite_aclk touch_gpio/s_axi_aclk \
    axi_dma_0/m_axi_mm2s_aclk axi_dma_0/m_axi_s2mm_aclk

pins ps/pl_clk0 neural/s_axi_aclk control_decode/aclk control_protocol/aclk
pins pixel_clock/output_clock pl_memory/aclk1

pins pl_ddr4/c0_ddr4_ui_clk pl_memory/aclk2
# Reset every fabric participant on loss of MIG/MMCM readiness or PS/button reset.
ip not_button xilinx.com:ip:util_vector_logic:*
set_property -dict [list CONFIG.C_OPERATION {not} CONFIG.C_SIZE {1}] [get_bd_cells not_button]
create_bd_port -dir I -type rst reset_n
set_property CONFIG.POLARITY ACTIVE_LOW [get_bd_ports reset_n]
connect_bd_net [get_bd_ports reset_n] [get_bd_pins not_button/Op1]
pins not_button/Res pl_ddr4/sys_rst
ip ready xilinx.com:ip:util_vector_logic:*
set_property -dict [list CONFIG.C_OPERATION {and} CONFIG.C_SIZE {1}] [get_bd_cells ready]
pins pixel_clock/locked ready/Op1
pins pl_ddr4/c0_init_calib_complete ready/Op2
ip common_reset xilinx.com:ip:util_vector_logic:*
set_property -dict [list CONFIG.C_OPERATION {and} CONFIG.C_SIZE {1}] [get_bd_cells common_reset]
pins ready/Res common_reset/Op1
ip button_ps_reset xilinx.com:ip:util_vector_logic:*
set_property -dict [list CONFIG.C_OPERATION {and} CONFIG.C_SIZE {1}] [get_bd_cells button_ps_reset]
connect_bd_net [get_bd_ports reset_n] [get_bd_pins button_ps_reset/Op1]
pins ps/pl_resetn0 button_ps_reset/Op2
pins button_ps_reset/Res common_reset/Op2
ip active_reset xilinx.com:ip:util_vector_logic:*
set_property -dict [list CONFIG.C_OPERATION {not} CONFIG.C_SIZE {1}] [get_bd_cells active_reset]
pins common_reset/Res active_reset/Op1
foreach {name clock} {gpu_reset ps/pl_clk0 pixel_reset pixel_clock/output_clock mig_reset pl_ddr4/c0_ddr4_ui_clk} {
    create_bd_cell -type module -reference rix_domain_reset $name
    pins $clock $name/clock
    pins button_ps_reset/Res $name/base_resetn
    pins pl_ddr4/c0_init_calib_complete $name/mig_ready
    pins pixel_clock/locked $name/pixel_locked
}
ip control_reset xilinx.com:ip:proc_sys_reset:*
pins ps/pl_clk0 control_reset/slowest_sync_clk
ip active_control_reset xilinx.com:ip:util_vector_logic:*
set_property -dict [list CONFIG.C_OPERATION {not} CONFIG.C_SIZE {1}] [get_bd_cells active_control_reset]
pins button_ps_reset/Res active_control_reset/Op1
pins active_control_reset/Res control_reset/ext_reset_in
ip one xilinx.com:ip:xlconstant:*
set_property CONFIG.CONST_VAL {1} [get_bd_cells one]
pins one/dout control_reset/dcm_locked

pins control_reset/peripheral_aresetn gpu/control_resetn control/aresetn touch_gpio/s_axi_aresetn neural/s_axi_aresetn control_decode/aresetn control_protocol/aresetn

pins gpu_reset/resetn gpu/gpu_resetn axi_dma_0/axi_resetn ps_memory/aresetn pl_memory/aresetn
pins gpu_reset/mig_status gpu/mig_ready
pins pixel_reset/resetn gpu/pixel_resetn
pins mig_reset/resetn pl_ddr4/c0_ddr4_aresetn
ip zero xilinx.com:ip:xlconstant:*
set_property CONFIG.CONST_VAL {0} [get_bd_cells zero]
ip irq xilinx.com:ip:xlconcat:*
set_property CONFIG.NUM_PORTS {8} [get_bd_cells irq]
pins axi_dma_0/mm2s_introut irq/In0
pins axi_dma_0/s2mm_introut irq/In1
pins touch_gpio/ip2intc_irpt irq/In2
foreach p {In3 In4 In5 In6 In7} {pins zero/dout irq/$p}
pins irq/dout ps/pl_ps_irq0
foreach {port source width} {lcd_hs gpu/lcd_hs 1 lcd_vs gpu/lcd_vs 1 lcd_de gpu/lcd_de 1 lcd_rgb gpu/lcd_rgb 24 fault gpu/fault 1 pixel_clk pixel_clock/output_clock 1} {
    if {$width>1} {create_bd_port -dir O -from [expr {$width-1}] -to 0 $port} else {create_bd_port -dir O $port}
    connect_bd_net [get_bd_ports $port] [get_bd_pins $source]
}
assign_bd_address

# Stage all control segments first: auto-assignment changes with new devices.
set cpu_segments {}
set staging 0xA0100000
foreach pattern {*axi_dma_0* *gpu* *touch_gpio* *neural*} {
 set segment [get_bd_addr_segs -of_objects [get_bd_addr_spaces ps/Data] -filter "NAME =~ $pattern"]
 if {[llength $segment]!=1} {error "Expected one CPU control segment for $pattern"}
 set_property offset $staging $segment
 set_property range 64K $segment
 lappend cpu_segments $segment
 set staging [expr {$staging+0x10000}]
}
foreach segment $cpu_segments address {0xA0000000 0xA0010000 0xA0020000 0xA0030000} {set_property offset $address $segment}
foreach seg [get_bd_addr_segs -hier -filter {NAME =~ *SEG_pl_ddr4*}] {
 if {![string match /ps/Data/* $seg]} {set_property offset 0x00000000 $seg;set_property range 1G $seg}
}
# PS MMIO view: MIG keeps low 30 address bits, so A1000000 aliases PL 21000000.
set cpu_view [get_bd_addr_segs -of_objects [get_bd_addr_spaces ps/Data] -filter {NAME =~ *pl_ddr4*}]
if {[llength $cpu_view]!=1} {error "Expected one CPU PL DDR view"}
set_property range 16M $cpu_view
set_property offset 0xA1000000 $cpu_view
save_bd_design
validate_bd_design
save_bd_design
write_bd_tcl -force [file join $root report minecraft-java-125 no-fsr-base-r1 rix_java256_nofsr_r1_validated.tcl]
make_wrapper -files [get_files rasterix_system.bd] -top
add_files [file join $out rix_java256_nofsr_r1.gen sources_1 bd rasterix_system hdl rasterix_system_wrapper.v]
add_files [file join $root src board axu3eg_rasterix_touch_top.v]
add_files -fileset constrs_1 [glob -directory [file join $root config] *.xdc]
set_property USED_IN_SYNTHESIS false [get_files rasterix_cdc.xdc]
set_property USED_IN_SYNTHESIS false [get_files rasterix_reset_cdc.xdc]
set_property top axu3eg_rasterix_touch_top [current_fileset]
update_compile_order -fileset sources_1
set ps_report [open [file join $root report minecraft-java-125 no-fsr-base-r1 neural_style_ps_parameters.txt] w]
foreach key {PSU__DDRC__BUS_WIDTH PSU__DDRC__DEVICE_CAPACITY PSU__DDRC__ROW_ADDR_COUNT PSU__DDRC__CL PSU__DDRC__CWL PSU__UART0__PERIPHERAL__IO PSU__SD1__PERIPHERAL__IO PSU__USB0__PERIPHERAL__IO PSU__USB0__RESET__IO PSU__ENET3__PERIPHERAL__IO PSU__QSPI__GRP_FBCLK__ENABLE} {
    puts $ps_report "$key=[get_property CONFIG.$key [get_bd_cells ps]]"
}
close $ps_report
set f [open [file join $root report minecraft-java-125 no-fsr-base-r1 neural_style_project.txt] w]
puts $f "mode=$mode\nconfig_sha256=$rix_config_hash\nps_base=$rix_ps_base\nverified=$rix_board_verified\nBD validation passed; physical board and boot pending"
close $f
puts "BOARD_BD_VALIDATION_PASS mode=$mode"

if {[llength [get_bd_cells -quiet fsr]]} {error "FSR IP unexpectedly present"}
if {[llength [get_bd_addr_segs -of_objects [get_bd_addr_spaces ps/Data] -filter {NAME =~ *fsr*}]]} {error "FSR address unexpectedly mapped"}
set proof [open [file join $root report minecraft-java-125 no-fsr-base-r1 bd-contract.txt] w]
puts $proof "fsr_present=0
geometry_frontend_present=0
TMU_count=2
profile_magic=0x4a324e31
feature_bits=0
geometry_bits=0
control_clocks=1
pl_memory_clocks=3
GPU_clock_MHz=100"
foreach pattern {*axi_dma_0* *gpu* *touch_gpio* *neural*} {
 set seg [get_bd_addr_segs -of_objects [get_bd_addr_spaces ps/Data] -filter "NAME =~ $pattern"]
 puts $proof "$pattern=[get_property OFFSET $seg]"
}
close $proof
report_property [get_bd_cells control] -file [file join $root report minecraft-java-125 no-fsr-base-r1 control-properties.txt]
puts "JAVA_NOFSR_R1_ADDRESSES_VALIDATED"

close_project


