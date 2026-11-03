// SPDX-License-Identifier: MIT
// Three learned 3x3 convolutions, 3 -> 8 -> 8 -> 3. Frame-buffered INT8
// inference, independent of the LCD pixel clock. 64 signed multipliers are
// reused over kernel positions/layers. One full frame plus two pending rows.
// Experimental in-place schedule; standalone acceptance is required before use.
// This module is a compute core; an AXI/DMA/display adapter is separate work.
module rix_cnn_engine #(
 parameter integer WIDTH=160, HEIGHT=96
)(
 input wire clk, rst,
 input wire cfg_restart, cfg_valid, cfg_commit,
 input wire [11:0] cfg_addr, input wire [31:0] cfg_data,
 output wire cfg_ready, output reg model_valid,
 input wire start, output wire busy, output reg fault,
 input wire [63:0] s_data, input wire s_valid, s_last, output wire s_ready,
 output wire [63:0] m_data, output wire m_valid, m_last, input wire m_ready,
 output reg done, output reg [31:0] compute_cycles
);
 localparam integer PIXELS=WIDTH*HEIGHT;
 localparam integer AW=$clog2(PIXELS+1);
 localparam PW=$clog2(2*WIDTH+1);
 localparam IDLE=0,LOAD=1,SEED=2,RUN=3,DRAIN=4,OUTREAD=5,OUTVALID=6,COPY=7,COPY_DRAIN=8;
 (* fsm_encoding="none" *) reg [3:0] state;
 reg [1:0] layer;
 reg [3:0] kernel;
 reg [15:0] x,y;
 reg [AW-1:0] position;
 reg [10:0] config_count;
 wire [11:0] expected_cfg=(config_count<1728)?config_count:
                         ((config_count<1752)?2048+(config_count-1728):2080+(config_count-1752));
 reg [2:0] cfg_oc,cfg_ic;
 reg [1:0] cfg_layer;
 reg [3:0] cfg_kernel;
 wire [5:0] cfg_bank={cfg_oc,cfg_ic};
 wire [4:0] cfg_word=cfg_layer*9+cfg_kernel;
 reg [767:0] biases;
 reg [4:0] shifts[0:23];
 (* ram_style="block" *) reg [63:0] pending_rows[0:2*WIDTH-1];
 wire [63:0] frame_read;
 reg [63:0] pending_read,quantized;
 wire issue=state==RUN;
 wire copy_issue=state==COPY;
 reg copy_valid,copy_tail;
 reg [15:0] copy_x;
 reg [PW-1:0] copy_row_base;
 reg [AW-1:0] copy_position,copy_write_address;
 reg read_valid,mult_valid,reduce_valid,final_valid,quant_valid;
 reg [AW-1:0] read_position,mult_position,reduce_position,final_position,quant_position;
 reg [PW-1:0] read_pending,mult_pending,reduce_pending,final_pending,quant_pending;
 reg [3:0] read_kernel,mult_kernel,reduce_kernel;
 wire load_write=state==LOAD&&s_valid&&!rst;
 wire frame_write=load_write||(copy_valid&&!rst);
 wire [AW-1:0] frame_write_address=load_write?position:copy_write_address;
 wire [63:0] frame_write_data=load_write?s_data:pending_read;
 wire frame_read_enable=(issue || state==OUTREAD)&&!rst;
 wire signed [15:0] products[0:63];
 reg signed [31:0] reduced[0:7],accumulator[0:15],final_sum[0:7];
 wire [63:0] features=frame_read;
 // Explicit banking is essential: a monolithic RAM with 64 dynamic read
 // ports can replicate the full weight memory 64 times during synthesis.
 genvar bank;
 generate for(bank=0;bank<64;bank=bank+1) begin: coefficient_banks
  (* ram_style="distributed" *) reg signed [7:0] coefficients[0:26];
  reg signed [7:0] coefficient_read;
  (* use_dsp="yes" *) wire signed [15:0] multiplication=$signed(features[(bank%8)*8+:8])*$signed(coefficient_read);
  reg signed [15:0] registered_product;
  assign products[bank]=registered_product;
  always @(posedge clk) begin
   if(!rst && cfg_valid && cfg_ready && !cfg_restart && config_count<1728 &&
      cfg_addr==expected_cfg && cfg_bank==bank) coefficients[cfg_word]<=cfg_data[7:0];
   if(issue&&!rst) coefficient_read<=coefficients[layer*9+kernel];
   if(read_valid&&!rst) registered_product<=multiplication;
  end
 end endgenerate
 assign cfg_ready=state==IDLE;
 assign busy=state!=IDLE;
 assign s_ready=state==LOAD;
 assign m_valid=state==OUTVALID;
 assign m_last=position==PIXELS-1;
 assign m_data=frame_read;

 // Replicate borders. No uninitialized halo is ever read.
 integer nx,ny;
 reg [AW-1:0] read_address;
 always @* begin
  nx=x;ny=y;
  case(kernel)
   0,3,6: if(x!=0) nx=x-1;
   2,5,8: if(x!=WIDTH-1) nx=x+1;
   default: nx=x;
  endcase
  case(kernel)
   0,1,2: if(y!=0) ny=y-1;
   6,7,8: if(y!=HEIGHT-1) ny=y+1;
   default: ny=y;
  endcase
  read_address=(state==OUTREAD)?position:ny*WIDTH+nx;
 end
 // Row writeback and convolution/output reads are separate phases. A single
 // shared address/enable makes the actual single-port RAM contract explicit.
 (* keep_hierarchy="yes" *) rix_cnn_inplace_frame_ram #(.DEPTH(PIXELS),.AW(AW)) frame_storage(
  .clk(clk),.enable(frame_write||frame_read_enable),.write_enable(frame_write),
  .address(frame_write?frame_write_address:read_address),.write_data(frame_write_data),.read_data(frame_read));
 always @(posedge clk) begin
  if(quant_valid&&!rst) pending_rows[quant_pending]<=quantized;
  if(copy_issue&&!rst) pending_read<=pending_rows[copy_row_base+copy_x];
 end

 // INT32 accumulator + signed 33-bit rounding; ties away from zero. Hidden
 // layers are ReLU and all layers saturate. Shift 0 is explicitly supported.
 function automatic [7:0] requantize;
  input signed [31:0] value;
  input [4:0] shift;
  input final_layer;
  reg signed [32:0] magnitude,rounded,scaled;
  begin
   magnitude=value<0?-$signed({value[31],value}):$signed({value[31],value});
   rounded=magnitude+(shift==0?33'sd0:(33'sd1<<<(shift-1)));
   scaled=rounded>>>shift;
   if(value<0) scaled=-scaled;
   if(scaled>127) requantize=8'h7f;
   else if(scaled<(final_layer?-128:0)) requantize=final_layer?8'h80:8'h00;
   else requantize=scaled[7:0];
  end
 endfunction

 integer oc,ic;
 always @(posedge clk) begin
  if(rst) begin
   state<=IDLE;layer<=0;kernel<=0;x<=0;y<=0;position<=0;
   config_count<=0;model_valid<=0;fault<=0;done<=0;compute_cycles<=0;
   cfg_oc<=0;cfg_ic<=0;cfg_layer<=0;cfg_kernel<=0;
   read_valid<=0;mult_valid<=0;reduce_valid<=0;final_valid<=0;quant_valid<=0;
   copy_valid<=0;copy_tail<=0;copy_x<=0;copy_row_base<=0;copy_position<=0;copy_write_address<=0;
  end else begin
   done<=0;
   if(state==SEED || state==RUN || state==DRAIN || state==COPY || state==COPY_DRAIN) compute_cycles<=compute_cycles+1;
   copy_valid<=copy_issue;
   if(copy_issue) copy_write_address<=copy_position;
   // Issue one kernel tap every cycle. Register synchronous feature/weight
   // reads, products, reduction, final accumulation and quantization. Two
   // accumulator slots let the next pixel start before the previous drains.
   read_valid<=issue;mult_valid<=read_valid;reduce_valid<=mult_valid;
   final_valid<=reduce_valid&&reduce_kernel==8;quant_valid<=final_valid;
   if(issue) begin read_position<=position;read_kernel<=kernel;read_pending<=y[0]?WIDTH+x:x;end
   if(read_valid) begin mult_position<=read_position;mult_kernel<=read_kernel;mult_pending<=read_pending;end
   if(mult_valid) begin
    reduce_position<=mult_position;reduce_kernel<=mult_kernel;reduce_pending<=mult_pending;
    for(oc=0;oc<8;oc=oc+1)
     reduced[oc]<=$signed({{16{products[oc*8+0][15]}},products[oc*8+0]})+
                  $signed({{16{products[oc*8+1][15]}},products[oc*8+1]})+
                  $signed({{16{products[oc*8+2][15]}},products[oc*8+2]})+
                  $signed({{16{products[oc*8+3][15]}},products[oc*8+3]})+
                  $signed({{16{products[oc*8+4][15]}},products[oc*8+4]})+
                  $signed({{16{products[oc*8+5][15]}},products[oc*8+5]})+
                  $signed({{16{products[oc*8+6][15]}},products[oc*8+6]})+
                  $signed({{16{products[oc*8+7][15]}},products[oc*8+7]});
   end
   if(issue&&kernel==0) for(oc=0;oc<8;oc=oc+1)
    accumulator[position[0]*8+oc]<=$signed(biases[(layer*8+oc)*32+:32]);
   if(reduce_valid) begin
    for(oc=0;oc<8;oc=oc+1) begin
     accumulator[reduce_position[0]*8+oc]<=accumulator[reduce_position[0]*8+oc]+reduced[oc];
     if(reduce_kernel==8) final_sum[oc]<=accumulator[reduce_position[0]*8+oc]+reduced[oc];
    end
    if(reduce_kernel==8) begin final_position<=reduce_position;final_pending<=reduce_pending;end
   end
   if(final_valid) begin
    quant_position<=final_position;quant_pending<=final_pending;
    for(oc=0;oc<8;oc=oc+1) quantized[oc*8+:8]<=requantize(final_sum[oc],shifts[layer*8+oc],layer==2);
   end
   // Model changes are accepted only while idle. Strict ordered loading makes
   // a partially loaded model uncommittable, including after fabric reset.
   if(cfg_restart && cfg_ready) begin
    config_count<=0;model_valid<=0;fault<=0;
    cfg_oc<=0;cfg_ic<=0;cfg_layer<=0;cfg_kernel<=0;
   end else if(cfg_valid && cfg_ready) begin
    model_valid<=0;
    if(config_count>=1776 || cfg_addr!=expected_cfg ||
       (config_count>=1752 && cfg_data>20)) begin fault<=1;config_count<=0;end
    else begin
     if(config_count<1728) begin
      if(cfg_ic==7) begin
       cfg_ic<=0;
       if(cfg_kernel==8) begin
        cfg_kernel<=0;
        if(cfg_oc==7) begin cfg_oc<=0;cfg_layer<=cfg_layer+1;end else cfg_oc<=cfg_oc+1;
       end else cfg_kernel<=cfg_kernel+1;
      end else cfg_ic<=cfg_ic+1;
     end
     else if(config_count<1752) biases[(config_count-1728)*32+:32]<=cfg_data;
     else shifts[config_count-1752]<=cfg_data[4:0];
     config_count<=config_count+1;
    end
   end else if(cfg_commit && cfg_ready) begin
    if(config_count==1776 && !fault) model_valid<=1;
    else begin fault<=1;model_valid<=0;end
   end
   case(state)
    IDLE: if(start) begin
     if(!model_valid || fault || cfg_restart || cfg_valid || cfg_commit) fault<=1;
     else begin state<=LOAD;position<=0;compute_cycles<=0;end
    end
    LOAD: if(s_valid) begin
     if(s_last!=(position==PIXELS-1)) begin fault<=1;state<=IDLE;end
     else if(position==PIXELS-1) begin
      layer<=0;position<=0;x<=0;y<=0;state<=SEED;
     end else position<=position+1;
    end
    SEED: begin
     kernel<=0;state<=RUN;
    end
    RUN: begin
     if(kernel==8) begin
      kernel<=0;
      if(x==WIDTH-1) state<=DRAIN;
      else begin
       position<=position+1;
       x<=x+1;
      end
     end else kernel<=kernel+1;
    end
    // Drain the final vector of this row before reusing pending storage.
    // At end of row y, every consumer of old row y-1 has completed.
    DRAIN: if(quant_valid&&quant_position==position) begin
     if(y!=0) begin
      copy_position<=position-(2*WIDTH-1);
      copy_row_base<=y[0]?0:WIDTH;
      copy_x<=0;copy_tail<=0;state<=COPY;
     end else if(HEIGHT==1) begin
      copy_position<=0;copy_row_base<=0;
      copy_x<=0;copy_tail<=1;state<=COPY;
     end else begin position<=position+1;x<=0;y<=y+1;state<=SEED;end
    end
    COPY: begin
     if(copy_x==WIDTH-1) state<=COPY_DRAIN;
     else begin copy_x<=copy_x+1;copy_position<=copy_position+1;end
    end
    // Last synchronous pending read is written to frame_bank on this edge.
    COPY_DRAIN: begin
     if(y==HEIGHT-1&&!copy_tail) begin
      copy_position<=position-(WIDTH-1);
      copy_row_base<=y[0]?WIDTH:0;
      copy_x<=0;copy_tail<=1;state<=COPY;
     end else if(y==HEIGHT-1) begin
      position<=0;x<=0;y<=0;
      if(layer==2) state<=OUTREAD;
      else begin layer<=layer+1;state<=SEED;end
     end else begin position<=position+1;x<=0;y<=y+1;state<=SEED;end
    end
    OUTREAD: state<=OUTVALID;
    OUTVALID: if(m_ready) begin
     if(position==PIXELS-1) begin state<=IDLE;done<=1;end
     else begin position<=position+1;state<=OUTREAD;end
    end
    default: begin fault<=1;state<=IDLE;end
   endcase
  end
 end
endmodule

// Dedicated synchronous, no-change-on-write memory. No reset or initialization
// of the array: the complete source frame is loaded before any compute read.
module rix_cnn_inplace_frame_ram #(parameter integer DEPTH=15360,AW=14)(
 input wire clk,enable,write_enable,
 input wire [AW-1:0] address,input wire [63:0] write_data,output reg [63:0] read_data
);
 (* ram_style="block" *) reg [63:0] memory[0:DEPTH-1];
 always @(posedge clk) if(enable) begin
  if(write_enable) memory[address]<=write_data;
  else read_data<=memory[address];
 end
endmodule
