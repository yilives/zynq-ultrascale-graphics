set root [file normalize [file join [file dirname [info script]] ..]]
set argv {fixed-v22-bankedscan}
source [file join $root scripts create_fsr_v22_board.tcl]
source [file join $root scripts build_fsr_v22_board.tcl]
