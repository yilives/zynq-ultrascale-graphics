// SPDX-License-Identifier: GPL-3.0-or-later
// Assert immediately even if the destination clock stops. Release only after
// five destination edges with all shared readiness signals continuously high.
module rix_domain_reset(
    (* X_INTERFACE_INFO="xilinx.com:signal:clock:1.0 clock CLK",
       X_INTERFACE_PARAMETER="ASSOCIATED_RESET resetn" *) input wire clock,
    input wire base_resetn,mig_ready,pixel_locked,
    (* X_INTERFACE_INFO="xilinx.com:signal:reset:1.0 resetn RST",
       X_INTERFACE_PARAMETER="POLARITY ACTIVE_LOW" *) output wire resetn,
    output wire mig_status
);
    // Synchronize each asynchronous source separately: no LUT combining clock
    // domains feeds a synchronizer. Combining the released outputs is local.
    (* ASYNC_REG="TRUE", SHREG_EXTRACT="NO" *) reg [3:0] base_pipe,mig_pipe,pixel_pipe;
    reg resetn_reg;
    wire released=base_pipe[3] && mig_pipe[3] && pixel_pipe[3];
    always @(posedge clock or negedge base_resetn) begin
        if(!base_resetn) base_pipe<=4'b0000;
        else base_pipe<={base_pipe[2:0],1'b1};
    end
    always @(posedge clock or negedge mig_ready) begin
        if(!mig_ready) mig_pipe<=4'b0000;
        else mig_pipe<={mig_pipe[2:0],1'b1};
    end
    always @(posedge clock or negedge pixel_locked) begin
        if(!pixel_locked) pixel_pipe<=4'b0000;
        else pixel_pipe<={pixel_pipe[2:0],1'b1};
    end
    // The local combination asserts immediately; a final local flop makes the
    // reset sent to other clock domains a single registered source.
    always @(posedge clock or negedge released) begin
        if(!released) resetn_reg<=1'b0;
        else resetn_reg<=1'b1;
    end
    // Reuse this chain for GPU status, avoiding two independent synchronizers
    // of the raw MIG ready signal in the same destination clock domain.
    assign mig_status=mig_pipe[3];
    assign resetn=resetn_reg;
endmodule
