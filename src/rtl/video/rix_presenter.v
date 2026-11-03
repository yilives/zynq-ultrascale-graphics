// SPDX-License-Identifier: GPL-3.0-or-later
// Bundled-data toggle CDC. Data held from request until acknowledged.
// Both domains must be reset together during startup or recovery.
module rix_presenter(
    input wire gpu_clk,gpu_rst,
    input wire present_valid,present_slot,
    input wire [31:0] frame_id,
    output reg present_ack,front_slot,
    output reg [31:0] presented_id,
    input wire pixel_clk,pixel_rst,safe_blank,scan_idle,
    output reg scan_valid,scan_slot,
    output reg [31:0] scan_frame_id
);
    reg req,ack,waiting,armed;
    reg held_slot;
    reg [31:0] held_id;
    (* ASYNC_REG="TRUE" *) reg [2:0] req_sync,ack_sync;
    reg seen;
    always @(posedge gpu_clk) begin
        if(gpu_rst) begin
            req<=0;ack_sync<=0;waiting<=0;armed<=1;held_slot<=0;held_id<=0;
            present_ack<=0;front_slot<=0;presented_id<=0;
        end else begin
            ack_sync<={ack_sync[1:0],ack};present_ack<=0;
            if(!present_valid) armed<=1;
            if(present_valid&&!waiting&&armed) begin
                held_slot<=present_slot;held_id<=frame_id;req<=!req;waiting<=1;armed<=0;
            end
            if(waiting&&ack_sync[2]==req) begin
                present_ack<=1;front_slot<=held_slot;presented_id<=held_id;waiting<=0;
            end
        end
    end
    always @(posedge pixel_clk) begin
        if(pixel_rst) begin
            req_sync<=0;seen<=0;ack<=0;scan_valid<=0;scan_slot<=0;scan_frame_id<=0;
        end else begin
            req_sync<={req_sync[1:0],req};
            if(req_sync[2]!=seen&&safe_blank&&scan_idle) begin
                scan_slot<=held_slot;scan_frame_id<=held_id;scan_valid<=1;
                seen<=req_sync[2];ack<=req_sync[2];
            end
        end
    end
endmodule
