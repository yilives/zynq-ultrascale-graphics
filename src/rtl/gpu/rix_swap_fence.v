// SPDX-License-Identifier: GPL-3.0-or-later
// RasterIX apply is a request pulse. Withdrawal is not display completion.
// Keep clear/commit ready when idle, but hold a swap until the bridge ack.
module rix_swap_fence(
 input wire clk,rst,request,completed,
 output wire ready
);
 localparam IDLE=0,WAIT_DONE=1,WAIT_RELEASE=2;
 reg [1:0] state;
 assign ready=completed||(state==IDLE&&!request)||(state==WAIT_RELEASE);
 always @(posedge clk) begin
  if(rst) state<=IDLE;
  else case(state)
   IDLE: if(request) state<=WAIT_DONE;
   WAIT_DONE: if(completed) state<=request?WAIT_RELEASE:IDLE;
   WAIT_RELEASE: if(!request) state<=IDLE;
   default: state<=WAIT_DONE; // Unexpected state must not acknowledge a swap.
  endcase
 end
endmodule
