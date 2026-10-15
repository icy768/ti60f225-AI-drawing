`timescale 1ns/1ps
module tb;
 reg uc=0,ac=0;always #3.333 uc=~uc;always #5 ac=~ac;
 reg rst=1,start=0;reg [1:0] bank=0;
 wire [23:0] pixel;wire valid,ready,busy;wire [31:0] errors,addr;
 wire av,ar,rr;reg rv=0,last=0;reg [127:0] data;reg [1:0] resp=0;
 integer cycle=0,ucycle=0,phase=0,delay_r=0,beat=0,word=0,count=0,checked=0,f;
 reg [31:0] saved;
 assign ready=ucycle%29<7;
 assign ar=phase==0&&cycle%7!=0;
 function [31:0] base(input [1:0] b);begin case(b)0:base=0;1:base='h200000;2:base='h800000;3:base='hc00000;endcase end endfunction
 function [23:0] px(input integer i);begin px=(32'h35a739*bank)^(32'h010307*i);end endfunction
 sc_replay #(.PIXELS(1024)) dut(uc,rst,ac,rst,start,bank,pixel,valid,ready,busy,errors,
  addr,av,ar,data,rv,last,resp,rr);
 always @(posedge ac)if(!rst)begin
  cycle<=cycle+1;
  if(av&&ar)begin
   if(addr!==base(bank)+word*16)$fatal(1,"Replay address bank=%0d addr=%h word=%0d",bank,addr,word);
   saved<=addr;phase<=1;delay_r<=cycle%17+1;beat<=0;word<=word+16;
  end
  if(phase==1)begin
   if(delay_r!=0)delay_r<=delay_r-1;
   else begin
    rv<=1;last<=beat==15;
    data<={8'd0,px((saved[19:4]+beat)*4+3),8'd0,px((saved[19:4]+beat)*4+2),8'd0,px((saved[19:4]+beat)*4+1),8'd0,px((saved[19:4]+beat)*4)};
    phase<=2;
   end
  end
  if(rv&&rr)begin
   rv<=0;
   if(last)phase<=0;
   else begin beat<=beat+1;phase<=1;delay_r<=cycle%3;end
  end
  if(rv&&!rr)$fatal(1,"Replay failed to reserve a whole burst");
 end
 always @(posedge uc)if(!rst)begin
  ucycle<=ucycle+1;
  if(valid&&ready)begin
   if(pixel!==px(count))$fatal(1,"Replay data bank=%0d pixel=%0d got=%h",bank,count,pixel);
   count<=count+1;checked<=checked+1;
  end
 end
 initial begin
  repeat(10)@(negedge ac);rst=0;
  for(f=0;f<4;f=f+1)begin
   @(negedge ac);bank=f;word=0;count=0;repeat(3)@(negedge ac);
   @(negedge uc);start=1;@(negedge uc);start=0;
   wait(busy);wait(!busy);repeat(12)@(negedge ac);
   if(count!=1024||word!=256||errors)$fatal(1,"Replay totals");
  end
  if(checked!=4096)$fatal(1,"Replay pixel count");
  rst=1;repeat(10)@(negedge ac);if(busy||valid||errors)$fatal(1,"Replay reset");
  $display("PASS replay four banks: 4096 exact pixels, 150/100 MHz, source stalls, sink backpressure, burst reservation, reset");$finish;
 end
 initial begin #2000000;$fatal(1,"Replay timeout");end
endmodule
