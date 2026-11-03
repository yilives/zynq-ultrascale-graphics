// SPDX-License-Identifier: GPL-3.0-or-later
// One explicitly leased PL snapshot. The bridge writes only after capture_start;
// READY is published after the last AXI B response. No new capture can start
// until release/expiry. Cancellation during a copy drains the existing copy.
module rix_frame_snapshot #(parameter LEASE_CYCLES=200000000)(
    input wire clk,rst,
    input wire request,release_snapshot,
    input wire [31:0] command_token,
    input wire capture_start,capture_done,capture_error,
    input wire [31:0] capture_frame_id,
    output wire pending,
    output wire [31:0] status,
    output reg [31:0] token,frame_id,expired_count
);
    localparam IDLE=0,PENDING=1,COPYING=2,READY=3;
    reg [1:0] state;
    reg canceled;
    reg [31:0] timer;
    wire releasing=release_snapshot&&command_token==token;
    wire expired=state!=IDLE&&timer==LEASE_CYCLES-1;
    assign pending=state==PENDING&&!releasing&&!expired;
    assign status={23'b0,canceled,6'b0,state};
    always @(posedge clk) begin
        if(rst) begin state<=IDLE;canceled<=0;timer<=0;token<=0;frame_id<=0;expired_count<=0;end
        else begin
            if(state==IDLE) timer<=0;
            else if(!canceled&&!expired) timer<=timer+1;
            if(expired&&!canceled) expired_count<=expired_count+1;
            case(state)
            IDLE: if(request&&command_token!=0&&command_token!=token) begin
                token<=command_token;state<=PENDING;timer<=0;canceled<=0;
            end
            PENDING: begin
                if(releasing||expired||capture_error) state<=IDLE;
                else if(capture_start) begin state<=COPYING;frame_id<=capture_frame_id;timer<=0;end
            end
            COPYING: begin
                if(releasing||expired) canceled<=1;
                if(capture_error) begin state<=IDLE;canceled<=0;end
                else if(capture_done) begin
                    state<=(canceled||releasing||expired)?IDLE:READY;
                    canceled<=0;timer<=0;
                end
            end
            READY: if(releasing||expired||capture_error) state<=IDLE;
            endcase
        end
    end
endmodule
