// SPDX-License-Identifier: GPL-3.0-or-later
// Automatic coherent snapshot of a multi-bit counter bus.
module rix_snapshot_cdc #(parameter WIDTH=64)(
    input wire src_clk,src_rst,
    input wire [WIDTH-1:0] src_data,
    input wire dst_clk,dst_rst,
    output reg [WIDTH-1:0] dst_data
);
    reg req,ack;
    reg [WIDTH-1:0] held;
    (* ASYNC_REG="TRUE" *) reg [2:0] req_sync,ack_sync;
    reg [9:0] interval;
    always @(posedge src_clk) begin
        if(src_rst) begin req_sync<=0;ack<=0;held<=0;end
        else begin
            req_sync<={req_sync[1:0],req};
            if(req_sync[2]!=ack) begin held<=src_data;ack<=req_sync[2];end
        end
    end
    always @(posedge dst_clk) begin
        if(dst_rst) begin req<=0;ack_sync<=0;dst_data<=0;interval<=0;end
        else begin
            ack_sync<={ack_sync[1:0],ack};
            if(ack_sync[2]==req) begin
                dst_data<=held;
                interval<=interval+1;
                if(interval==1023) req<=!req;
            end
        end
    end
endmodule
