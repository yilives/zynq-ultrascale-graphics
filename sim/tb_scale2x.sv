`timescale 1ns/1ps
module tb_scale2x;
    reg clk=0;always #5 clk=~clk;
    reg rst=1,prepare=0,in_valid=0,hs=0,vs=0,de=0;
    reg [23:0] in_rgb=0;
    reg [11:0] x=0,y=0;
    wire in_ready,out_hs,out_vs,out_de,dropped;
    wire [23:0] out_rgb;
    wire [31:0] underflow_count;
    scale2x_nearest #(.WIDTH(4),.HEIGHT(3)) dut(.*);
    integer row,col,j;
    task feed(input integer r);
        begin
            for(j=0;j<4;j=j+1) begin
                @(negedge clk);in_valid=1;in_rgb=r*16+j;
                while(!in_ready) @(negedge clk);
                @(posedge clk);
            end
            @(negedge clk);in_valid=0;
        end
    endtask
    initial begin
        repeat(4) @(negedge clk);rst=0;prepare=1;
        @(negedge clk);prepare=0;
        feed(0);feed(1);
        for(row=0;row<6;row=row+1) begin
            for(col=0;col<8;col=col+1) begin
                @(negedge clk);de=1;x=col;y=row;hs=col[0];vs=row[0];
                @(posedge clk);#1;
                if(out_rgb!==(row/2)*16+col/2||out_de!=de||out_hs!=hs||out_vs!=vs||dropped) $fatal(1,"Scale/timing mismatch row %d col %d rgb %h",row,col,out_rgb);
            end
            @(negedge clk);de=0;
            if(row==1) feed(2);
        end
        @(negedge clk);prepare=1;
        @(negedge clk);prepare=0;de=1;x=0;y=0;
        repeat(4) @(negedge clk);
        if(!dropped||underflow_count!=1||out_rgb!=0) $fatal(1,"Underflow containment");
        de=0;prepare=1;@(negedge clk);prepare=0;feed(0);
        @(negedge clk);de=1;x=0;y=0;@(posedge clk);#1;
        if(dropped||out_rgb!=0) $fatal(1,"Prepare recovery");
        $display("PASS scale2x: horizontal/vertical repeat, row reuse, timing alignment, underflow and prepare recovery");$finish;
    end
    initial begin #100000;$fatal(1,"Watchdog");end
endmodule
