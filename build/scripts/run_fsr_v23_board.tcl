set root [file normalize [file join [file dirname [info script]] ..]]
set argv {fixed-v23-bufferedread}
source [file join $root scripts create_fsr_v23_board.tcl]
source [file join $root scripts build_fsr_v23_board.tcl]
