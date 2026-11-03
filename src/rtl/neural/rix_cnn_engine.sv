// SPDX-License-Identifier: MIT
// Three learned 3x3 convolutions, 3 -> 8 -> 8 -> 3. Frame-buffered INT8
// inference, independent of the LCD pixel clock. 64 signed multipliers are
// reused over kernel positions/layers. Two synchronous 64-bit feature banks.
// This module is a compute core; an AXI/DMA/display adapter is separate work.
module rix_cnn_engine #(
 parameter integer WIDTH=160, HEIGHT=96, BANKS=64
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
 // BANKS physical MAC lanes time-share the 64 output/input channel pairs.
 // BANKS must be a multiple of eight so each phase owns whole output channels.
 localparam integer PHASES=(64+BANKS-1)/BANKS;
 localparam integer GROUPS=(BANKS+7)/8;
 localparam integer OUTPUTS_PER_PHASE=BANKS/8;
 localparam integer PHASE_W=(PHASES<=1)?1:$clog2(PHASES);
 localparam IDLE=0,LOAD=1,SEED=2,RUN=3,DRAIN=4,OUTREAD=5,OUTVALID=6;
 reg [3:0] state;
 reg [1:0] layer;
 reg [3:0] kernel;
 reg [PHASE_W-1:0] phase;
 reg [15:0] x,y;
 reg [AW-1:0] position;
 reg [10:0] config_count;
 wire [11:0] expected_cfg=(config_count<1728)?config_count:
                         ((config_count<1752)?2048+(config_count-1728):2080+(config_count-1752));
 reg [2:0] cfg_oc,cfg_ic;
 reg [1:0] cfg_layer;
 reg [3:0] cfg_kernel;
 wire [5:0] cfg_physical_bank=(cfg_oc%OUTPUTS_PER_PHASE)*8+cfg_ic;
 wire [PHASE_W-1:0] cfg_phase_index=cfg_oc/OUTPUTS_PER_PHASE;
 wire [4:0] cfg_word=cfg_layer*9+cfg_kernel;
 reg [767:0] biases;
 reg [4:0] shifts[0:23];
 (* ram_style="block" *) reg [63:0] bank0[0:PIXELS-1];
 (* ram_style="block" *) reg [63:0] bank1[0:PIXELS-1];
 reg [63:0] bank0_read,bank1_read,quantized;
 wire issue=state==RUN;
 reg read_valid,mult_valid,reduce_valid,final_valid,quant_valid;
 reg [AW-1:0] read_position,mult_position,reduce_position,final_position,quant_position;
 reg [3:0] read_kernel,mult_kernel,reduce_kernel;
 reg [PHASE_W-1:0] read_phase,mult_phase,reduce_phase;
 wire bank0_load=state==LOAD&&s_valid&&!rst;
 wire bank0_write=bank0_load||(quant_valid&&layer==1&&!rst);
 wire [AW-1:0] bank0_write_address=bank0_load?position:quant_position;
 wire [63:0] bank0_write_data=bank0_load?s_data:quantized;
 wire signed [15:0] products[0:BANKS-1];
 reg [32*GROUPS-1:0] reduced;
 reg [16*32-1:0] accumulator;
 reg [8*32-1:0] final_sum;
 wire [63:0] features=layer==1?bank1_read:bank0_read;
 // Keep each logical (output,input) weight bank local to one physical MAC.
 // Reduced BANKS values time-share coefficient phases instead of dropping
 // channels; this preserves the 64 logical weight banks for every layer.
 genvar bank;
 generate for(bank=0;bank<BANKS;bank=bank+1) begin: coefficient_banks
  localparam integer LANE_PHASES=((63-bank)/BANKS)+1;
  // Store phase-major in one dimension. Vivado does not infer memories from
  // the previous unpacked 2-D declaration and reports the flattened array as
  // a problematic 3-D RAM. The flat address keeps phase/tap selection explicit.
  (* ram_style="distributed" *) reg signed [7:0] coefficients[0:LANE_PHASES*27-1];
  reg signed [7:0] coefficient_read;
  (* use_dsp="yes" *) wire signed [15:0] multiplication=$signed(features[(bank%8)*8+:8])*$signed(coefficient_read);
  reg signed [15:0] registered_product;
  wire cfg_lane_write=cfg_physical_bank==bank;
  wire [PHASE_W-1:0] cfg_lane_phase=cfg_phase_index;
  assign products[bank]=registered_product;
  always @(posedge clk) begin
   if(!rst && cfg_valid && cfg_ready && !cfg_restart && config_count<1728 && cfg_addr==expected_cfg && cfg_lane_write)
    coefficients[cfg_lane_phase*27+cfg_word]<=cfg_data[7:0];
   if(issue&&!rst) coefficient_read<=phase<LANE_PHASES?coefficients[phase*27+layer*9+kernel]:8'sd0;
   if(read_valid&&!rst)
    registered_product<=((read_phase*BANKS+bank)<64)?multiplication:16'sd0;
  end
 end endgenerate
 assign cfg_ready=state==IDLE;
 assign busy=state!=IDLE;
 assign s_ready=state==LOAD;
 assign m_valid=state==OUTVALID;
 assign m_last=position==PIXELS-1;
 assign m_data=bank1_read;

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
 always @(posedge clk) begin
  if((issue || state==OUTREAD)&&!rst) begin
   bank0_read<=bank0[read_address];bank1_read<=bank1[read_address];
  end
  if(bank0_write) bank0[bank0_write_address]<=bank0_write_data;
  if(quant_valid&&layer!=1&&!rst) bank1[quant_position]<=quantized;
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
   state<=IDLE;layer<=0;kernel<=0;phase<=0;x<=0;y<=0;position<=0;
   config_count<=0;model_valid<=0;fault<=0;done<=0;compute_cycles<=0;
   cfg_oc<=0;cfg_ic<=0;cfg_layer<=0;cfg_kernel<=0;
   read_valid<=0;mult_valid<=0;reduce_valid<=0;final_valid<=0;quant_valid<=0;
   read_phase<=0;mult_phase<=0;reduce_phase<=0;
  end else begin
   done<=0;
   if(state==SEED || state==RUN || state==DRAIN) compute_cycles<=compute_cycles+1;
   // Issue one kernel tap per phase. Register synchronous feature/weight
   // reads, products, reduction, final accumulation and quantization. Two
   // accumulator slots let the next pixel start before the previous drains.
   read_valid<=issue;mult_valid<=read_valid;reduce_valid<=mult_valid;
   final_valid<=reduce_valid&&reduce_kernel==8&&reduce_phase==PHASES-1;
   quant_valid<=final_valid;
   if(issue) begin read_position<=position;read_kernel<=kernel;read_phase<=phase;end
   if(read_valid) begin mult_position<=read_position;mult_kernel<=read_kernel;mult_phase<=read_phase;end
   if(mult_valid) begin
    reduce_position<=mult_position;reduce_kernel<=mult_kernel;reduce_phase<=mult_phase;
    for(oc=0;oc<GROUPS;oc=oc+1)
     reduced[oc*32+:32]<=$signed({{16{products[oc*8+0][15]}},products[oc*8+0]})+
                  $signed({{16{products[oc*8+1][15]}},products[oc*8+1]})+
                  $signed({{16{products[oc*8+2][15]}},products[oc*8+2]})+
                  $signed({{16{products[oc*8+3][15]}},products[oc*8+3]})+
                  $signed({{16{products[oc*8+4][15]}},products[oc*8+4]})+
                  $signed({{16{products[oc*8+5][15]}},products[oc*8+5]})+
                  $signed({{16{products[oc*8+6][15]}},products[oc*8+6]})+
                  $signed({{16{products[oc*8+7][15]}},products[oc*8+7]});
   end
   if(issue&&kernel==0) for(oc=0;oc<GROUPS;oc=oc+1)
    if(phase*GROUPS+oc<8)
     accumulator[(position[0]*8+phase*GROUPS+oc)*32+:32]<=
      $signed(biases[(layer*8+phase*GROUPS+oc)*32+:32]);
   if(reduce_valid) begin
    for(oc=0;oc<GROUPS;oc=oc+1) if(reduce_phase*GROUPS+oc<8) begin
     accumulator[(reduce_position[0]*8+reduce_phase*GROUPS+oc)*32+:32]<=
      accumulator[(reduce_position[0]*8+reduce_phase*GROUPS+oc)*32+:32]+$signed(reduced[oc*32+:32]);
     if(reduce_kernel==8)
      final_sum[(reduce_phase*GROUPS+oc)*32+:32]<=
       accumulator[(reduce_position[0]*8+reduce_phase*GROUPS+oc)*32+:32]+$signed(reduced[oc*32+:32]);
    end
    if(reduce_kernel==8 && reduce_phase==PHASES-1) final_position<=reduce_position;
   end
   if(final_valid) begin
    quant_position<=final_position;
    for(oc=0;oc<8;oc=oc+1) quantized[oc*8+:8]<=requantize($signed(final_sum[oc*32+:32]),shifts[layer*8+oc],layer==2);
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
      layer<=0;phase<=0;position<=0;x<=0;y<=0;state<=SEED;
     end else position<=position+1;
    end
    SEED: begin
     kernel<=0;phase<=0;state<=RUN;
    end
    RUN: begin
     if(phase==PHASES-1) begin
      phase<=0;
      if(kernel==8) begin
       kernel<=0;
       if(position==PIXELS-1) state<=DRAIN;
       else begin
        position<=position+1;
        if(x==WIDTH-1) begin x<=0;y<=y+1;end else x<=x+1;
       end
      end else kernel<=kernel+1;
     end else phase<=phase+1;
    end
    DRAIN: if(quant_valid&&quant_position==PIXELS-1) begin
     position<=0;phase<=0;x<=0;y<=0;
     if(layer==2) state<=OUTREAD;
     else begin layer<=layer+1;state<=SEED;end
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
