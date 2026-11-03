`timescale 1ns/1ps
module tb_display;
    reg clk=0,pixel_clk=0;
    always #5 clk=~clk;
    always #7 pixel_clk=~pixel_clk;
    reg rst=1,swap_fb=0,enable=1,mig_ready=1,lcd_running=1;
    reg [31:0] fb_addr=32'h10000000;
    reg [19:0] fb_size=8;
    wire fb_swapped,present_valid,present_slot,copy_done,fault,front_slot,present_ack;
    wire [31:0] frame_id,presented_id,swap_count,copy_count,present_count,read_errors,write_errors,timeouts;
    wire [7:0] first_error;
    wire [31:0] m_ps_araddr,m_pl_awaddr;
    wire [31:0] completed_source_base;
    wire snapshot_pending=1'b0;
    wire snapshot_start,snapshot_done,snapshot_error;
    reg [31:0] expected_source=32'h10000000;
    wire [7:0] m_ps_arlen,m_pl_awlen;
    wire [2:0] m_ps_arsize,m_pl_awsize;
    wire [1:0] m_ps_arburst,m_pl_awburst;
    wire m_ps_arvalid,m_ps_rready,m_pl_awvalid,m_pl_wvalid,m_pl_wlast,m_pl_bready;
    wire [127:0] m_pl_wdata;
    wire [15:0] m_pl_wstrb;
    reg m_ps_arready=0,m_ps_rlast=1,m_ps_rvalid=0,m_pl_awready=0,m_pl_wready=0,m_pl_bvalid=0;
    reg [63:0] m_ps_rdata=64'hffff001f07e0f800;
    reg [1:0] m_ps_rresp=0,m_pl_bresp=0;
    reg safe_blank=0,scan_idle=0;
    wire scan_valid,scan_slot;
    wire [31:0] scan_frame_id;
    integer cycle=0,reads=0,writes=0,delay_b=0,delay_r=0;
    reg saw_aw=0,saw_w=0,inject_read_error=0,inject_write_error=0,freeze=0;
    rix_frame_bridge #(.WIDTH(4),.HEIGHT(2),.PS_GFX_BASE(32'h10000000),.TIMEOUT_CYCLES(300),.BURST_BEATS(1)) dut(.*);
    rix_presenter presenter(.gpu_clk(clk),.gpu_rst(rst),.present_valid(present_valid),.present_slot(present_slot),
        .frame_id(frame_id),.present_ack(present_ack),.front_slot(front_slot),.presented_id(presented_id),
        .pixel_clk(pixel_clk),.pixel_rst(rst),.safe_blank(safe_blank),.scan_idle(scan_idle),
        .scan_valid(scan_valid),.scan_slot(scan_slot),.scan_frame_id(scan_frame_id));
    // Independent AW/W stalls, delayed last write response.
    always @(negedge clk) begin
        cycle=cycle+1;
        m_ps_arready=!freeze&&(cycle%3!=0);
        m_pl_awready=!freeze&&(cycle%4==0);
        m_pl_wready=!freeze&&(cycle%5!=0);
    end
    always @(posedge clk) begin
        if(rst) begin reads<=0;writes<=0;delay_r<=0;delay_b<=0;m_ps_rvalid<=0;m_pl_bvalid<=0;saw_aw<=0;saw_w<=0;end
        else begin
            if(m_ps_arvalid&&m_ps_arready) begin
                if(m_ps_araddr!=expected_source+reads*8||m_ps_araddr[2:0]||m_ps_arlen!=0) $fatal(1,"AR layout");
                reads<=reads+1;delay_r<=3;m_ps_rresp<=inject_read_error?2:0;
            end
            if(delay_r>0) begin delay_r<=delay_r-1;if(delay_r==1) m_ps_rvalid<=1;end
            if(m_ps_rvalid&&m_ps_rready) m_ps_rvalid<=0;
            if(m_pl_awvalid&&m_pl_awready) begin
                if(m_pl_awaddr!=(front_slot?0:32'h100000)+writes*16||m_pl_awaddr[3:0]||m_pl_awlen!=0) $fatal(1,"AW layout");
                saw_aw<=1;
            end
            if(m_pl_wvalid&&m_pl_wready) begin
                if(m_pl_wdata!==128'h00ffffff000000ff0000ff0000ff0000||m_pl_wstrb!=16'hffff||!m_pl_wlast) $fatal(1,"RGB565 expansion");
                saw_w<=1;
            end
            if(saw_aw&&saw_w&&!delay_b&&!m_pl_bvalid) begin delay_b<=17;saw_aw<=0;saw_w<=0;end
            if(delay_b>0) begin
                if(copy_done||present_valid||fb_swapped) $fatal(1,"Presented before B response");
                delay_b<=delay_b-1;
                if(delay_b==1) begin m_pl_bvalid<=1;m_pl_bresp<=inject_write_error?2:0;end
            end
            if(m_pl_bvalid&&m_pl_bready) begin m_pl_bvalid<=0;writes<=writes+1;end
        end
    end
    task reset_test;
        begin
            @(negedge clk);rst=1;swap_fb=0;safe_blank=0;scan_idle=0;freeze=0;
            repeat(6) @(negedge clk);rst=0;repeat(2) @(negedge clk);
        end
    endtask
    integer i;
    initial begin
        reset_test();
        // 1000 complete swaps with asynchronous pixel clock and scan ownership.
        for(i=0;i<1000;i=i+1) begin
            reads=0;writes=0;swap_fb=1;safe_blank=0;scan_idle=0;
            wait(present_valid);repeat(10) @(negedge clk);
            if(fb_swapped||present_count!=i) $fatal(1,"Swap before safe blank");
            safe_blank=1;repeat(8) @(negedge clk);
            if(fb_swapped||present_count!=i) $fatal(1,"Released old slot with outstanding scan");
            scan_idle=1;wait(fb_swapped);@(negedge clk);
            if(presented_id!=i+1||fault||copy_count!=i+1||writes!=2) $fatal(1,"Frame ownership/counters");
            swap_fb=0;repeat(5) @(negedge clk);
        end
        // The renderer may change its live register while a copy is pending.
        // Metadata must still identify the slot actually read by the bridge.
        reset_test();fb_addr=32'h10100000;expected_source=fb_addr;swap_fb=1;
        wait(m_ps_arvalid&&m_ps_arready);@(negedge clk);fb_addr=32'h1021f400;
        wait(copy_done);#1;
        if(completed_source_base!==expected_source)$fatal(1,"Completed source followed upstream tile address");
        safe_blank=1;scan_idle=1;wait(fb_swapped);@(negedge clk);swap_fb=0;
        repeat(5)@(negedge clk);fb_addr=32'h10000000;expected_source=fb_addr;
        reset_test();inject_read_error=1;swap_fb=1;wait(fault);repeat(5) @(negedge clk);
        if(first_error!=2||copy_count||present_count||fb_swapped) $fatal(1,"Read error published");
        inject_read_error=0;reset_test();inject_write_error=1;swap_fb=1;wait(fault);repeat(5) @(negedge clk);
        if(first_error!=3||copy_count||present_count) $fatal(1,"Write error published");
        inject_write_error=0;reset_test();fb_addr=32'hdeadbeef;swap_fb=1;wait(fault);
        if(first_error!=1||reads||writes) $fatal(1,"Invalid source accepted");
        fb_addr=32'h10000000;reset_test();freeze=1;swap_fb=1;wait(fault);
        if(first_error!=4||timeouts!=1||copy_count||present_count||!m_ps_arvalid) $fatal(1,"Timeout or AXI valid dropped");
        freeze=0;repeat(30) @(negedge clk);
        if(copy_count||present_count) $fatal(1,"Timed out frame published after drain");
        $display("PASS display: 1000 swaps, completed source despite upstream tile changes, delayed B, independent stalls, blank/idle CDC, read/write errors, address rejection, timeout drain");$finish;
    end
    initial begin #10000000;$fatal(1,"Watchdog");end
endmodule
