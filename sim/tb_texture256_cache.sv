module tb_texture256_cache;
timeunit 1ns; timeprecision 1ps;
reg clk=0;always #5 clk=~clk;
reg resetn=0,valid=0,out_ready=0,page_valid=0,page_last=0,nearest=0;
reg [16:0] a00=0,a01=0,a10=0,a11=0;
reg [31:0] page_data=0;
wire ready,out_valid,page_ready;
wire [15:0] q00,q01,q10,q11;
wire [5:0] arid;
wire [31:0] araddr;
wire [7:0] arlen;
wire [2:0] arsize,arprot;
wire [1:0] arburst;
wire arlock,arvalid;
wire [3:0] arcache;
reg busy=0,rvalid=0,rlast=0;
reg [63:0] rdata=0;
reg [5:0] rid=0;
reg [31:0] address=0;
integer remaining=0,cycles=0,reads=0,checked=0;
wire arready=!busy&&(cycles%7!=0);
wire rready;
TextureReader #(.DATA_WIDTH(64),.TEXEL_WIDTH(16),.ID_WIDTH(6),
 .ADDR_WIDTH(32),.PAGE_SIZE(2048),.CACHE_SIZE(1024)) dut(
 .aclk(clk),.resetn(resetn),.enable(1'b1),.nearest(nearest),
 .s_tr_valid(valid),.s_tr_ready(ready),.s_tr_addr_00(a00),.s_tr_addr_01(a01),
 .s_tr_addr_10(a10),.s_tr_addr_11(a11),
 .m_tr_valid(out_valid),.m_tr_ready(out_ready),.m_tr_texel_00(q00),
 .m_tr_texel_01(q01),.m_tr_texel_10(q10),.m_tr_texel_11(q11),
 .s_axis_tvalid(page_valid),.s_axis_tready(page_ready),.s_axis_tlast(page_last),.s_axis_tdata(page_data),
 .m_axi_arid(arid),.m_axi_araddr(araddr),.m_axi_arlen(arlen),.m_axi_arsize(arsize),
 .m_axi_arburst(arburst),.m_axi_arlock(arlock),.m_axi_arcache(arcache),
 .m_axi_arprot(arprot),.m_axi_arvalid(arvalid),.m_axi_arready(arready),
 .m_axi_rid(rid),.m_axi_rdata(rdata),.m_axi_rresp(2'b0),
 .m_axi_rlast(rlast),.m_axi_rvalid(rvalid),.m_axi_rready(rready));
function automatic [15:0] gold(input integer index,input integer epoch);
 gold=(index&65535)^((index>>16)*16'h1f17)^(epoch?16'ha55a:16'h0000);
endfunction
function automatic [15:0] memory_texel(input [31:0] physical);
 integer epoch,page,index;
 begin
  if(physical[31:28]!=4'h4 && physical[31:28]!=4'h5) $fatal(1,"Bad physical address %h",physical);
  if(physical[11]) $fatal(1,"Read entered unmapped half-page %h",physical);
  epoch=(physical[31:28]==4'h5);
  page=((physical&32'h0fffffff)>>12)^32'h55;
  index=(page*2048+(physical&2047))/2;
  memory_texel=gold(index,epoch);
 end
endfunction
always @(posedge clk) begin
 cycles<=cycles+1;
 if(!resetn) begin busy<=0;rvalid<=0;rlast<=0;remaining<=0;end
 else if(arvalid&&arready) begin
  if(arsize!=3 || arburst!=1 || araddr[4:0]!=0 || arlen!=3)
    $fatal(1,"Unexpected AXI burst %h len=%d size=%d",araddr,arlen,arsize);
  busy<=1;address<=araddr;remaining<=arlen+1;rid<=arid;rvalid<=0;reads<=reads+1;
 end else if(busy) begin
  if(rvalid&&rready) begin
   rvalid<=0;remaining<=remaining-1;address<=address+8;
   if(rlast) begin busy<=0;rlast<=0;end
  end
  if(!rvalid && cycles%5!=0) begin
   rdata<={memory_texel(address+6),memory_texel(address+4),memory_texel(address+2),memory_texel(address)};
   rvalid<=1;rlast<=(remaining==1);
  end
 end
end
task automatic program_pages(input integer epoch);
 integer p;
 begin
  for(p=0;p<128;p=p+1) begin
   @(negedge clk);page_valid=1;page_last=(p==127);
   page_data=(epoch?32'h50000000:32'h40000000)+((p^32'h55)*4096);
   @(posedge clk);while(!page_ready) @(posedge clk);
  end
  @(negedge clk);page_valid=0;page_last=0;
  repeat(64) @(posedge clk);
 end
endtask
task automatic quad(input integer i0,input integer i1,input integer i2,input integer i3,input integer epoch);
 reg [63:0] held;
 begin
  @(negedge clk);a00=i0;a01=i1;a10=i2;a11=i3;valid=1;out_ready=0;
  @(posedge clk);while(!ready) @(posedge clk);
  @(negedge clk);valid=0;
  @(posedge clk);while(!out_valid) @(posedge clk);
  held={q11,q10,q01,q00};
  repeat(3) begin
   @(posedge clk);
   if(!out_valid || held!=={q11,q10,q01,q00}) $fatal(1,"Output unstable during backpressure");
  end
  if(q00!==gold(i0,epoch)||(!nearest&&(q01!==gold(i1,epoch)||q10!==gold(i2,epoch)||q11!==gold(i3,epoch))))
   $fatal(1,"Texel mismatch i=%d/%d/%d/%d epoch=%d got=%h expected=%h",i0,i1,i2,i3,epoch,held,
    {gold(i3,epoch),gold(i2,epoch),gold(i1,epoch),gold(i0,epoch)});
  @(negedge clk);out_ready=1;
  @(posedge clk);
  @(negedge clk);out_ready=0;
  checked=checked+1;
 end
endtask
integer x,y,i;
initial begin
 repeat(8) @(posedge clk);@(negedge clk);resetn=1;
 program_pages(0);
 for(y=0;y<256;y=y+1) begin
  for(x=0;x<256;x=x+1)
   quad(y*256+x,y*256+((x+1)%256),((y+1)%256)*256+x,((y+1)%256)*256+((x+1)%256),0);
  if(y%64==63) $display("TEXTURE256_ROWS_CHECKED %d",y+1);
 end
 // Every mip texel, including addresses above 65535 and partial final pages.
 for(i=65536;i<87381;i=i+1) quad(i,i,i,i,0);
 quad(127,128,65535,65536,0);
 program_pages(1);
 quad(127,128,65535,65536,1);
 for(i=0;i<4096;i=i+1) begin
  x=(i*4051)&65535;quad(x,x,x,x,1);
 end
 @(negedge clk);nearest=1;
 for(i=0;i<4096;i=i+1) begin
  x=(i*4051)&65535;quad(x,(x+1)&65535,(x+256)&65535,(x+257)&65535,1);
 end
 $display("PASS TEXTURE256 full_base_texels=65536 mip_texels=21845 quads=%d axi_bursts=%d cycles=%d source_resampled=0",checked,reads,cycles);
 $finish;
end
initial begin #200000000;$fatal(1,"Texture cache simulation watchdog");end
endmodule
