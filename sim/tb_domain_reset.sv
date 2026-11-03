`timescale 1ns/1ps
module tb_domain_reset;
    reg gpu=0,pixel=0,mig=0,pixel_run=1;
    reg base=0,mig_ready=0,locked=0;
    wire gpu_n,pixel_n,mig_n;
    always #5 gpu=~gpu;
    always #15 if(pixel_run) pixel=~pixel;
    always #2.5 mig=~mig;
    rix_domain_reset a(.clock(gpu),.base_resetn(base),.mig_ready(mig_ready),.pixel_locked(locked),.resetn(gpu_n),.mig_status());
    rix_domain_reset b(.clock(pixel),.base_resetn(base),.mig_ready(mig_ready),.pixel_locked(locked),.resetn(pixel_n),.mig_status());
    rix_domain_reset c(.clock(mig),.base_resetn(base),.mig_ready(mig_ready),.pixel_locked(locked),.resetn(mig_n),.mig_status());
    task all_low;
        if({gpu_n,pixel_n,mig_n}!==3'b000) $fatal(1,"Reset not asserted in all domains");
    endtask
    task all_high;
        if({gpu_n,pixel_n,mig_n}!==3'b111) $fatal(1,"Reset not released in all domains");
    endtask
    initial begin
        #1; all_low();
        base=1; #50; all_low();
        mig_ready=1; #50; all_low();
        locked=1; #2;
        if(gpu_n || pixel_n) $fatal(1,"Reset released before synchronizer edges");
        repeat(4) @(posedge gpu);
        #1; if(gpu_n) $fatal(1,"GPU reset released before fifth edge");
        @(posedge gpu); #1;
        if(!gpu_n) $fatal(1,"GPU reset did not release on fifth edge");
        #170; all_high();
        pixel_run=0; mig_ready=0; #1; all_low();
        mig_ready=1; #60;
        if(!gpu_n || !mig_n || pixel_n) $fatal(1,"Stopped clock reset behavior incorrect");
        pixel_run=1; #170; all_high();
        base=0; #1; all_low();
        #23; base=1; #2; all_low();
        #170; all_high();
        locked=0; #1; all_low();
        $display("DOMAIN_RESET_PASS: asynchronous assert, five-edge release, stopped clock and readiness loss");
        $finish;
    end
    initial begin #2000; $fatal(1,"Test timeout"); end
endmodule
