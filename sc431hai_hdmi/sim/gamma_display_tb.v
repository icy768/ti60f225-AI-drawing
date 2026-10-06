`timescale 1ns/1ps
module gamma_display_tb;

reg clk=0; always #5 clk=~clk;
reg rstn=0,valid=0,hs=0,vs=0;
reg [9:0] r=0,g=0,b=0;
wire [9:0] r10,g10,b10;
wire [7:0] r8,g8,b8;
wire v10,h10,s10,v8,h8,s8;
gamma_correction #(.DATA_WIDTH(10)) d10(clk,rstn,valid,hs,vs,r,g,b,r10,g10,b10,v10,h10,s10);
gamma_correction #(.DATA_WIDTH(8)) d8(clk,rstn,valid,hs,vs,r[7:0],g[7:0],b[7:0],r8,g8,b8,v8,h8,s8);
function integer encode;
input integer x,maximum;
integer address,value;
begin
 address=(maximum==255) ? (x*4+x/64) : x;
 value=$rtoi(1023.0*((1.0*address/1023.0)**(1.0/2.2))+0.5);
 encode=(maximum==255) ? value/4 : value;
end
endfunction
function integer expected;
input integer x,y,z,maximum;
begin expected=encode(x,maximum);end
endfunction
task check;
input integer actual,wanted;
begin
 if ((actual != wanted) || (^actual === 1'bx)) begin
  $display("FAIL got %d expected %d",actual,wanted);$fatal(1);
 end
end
endtask
task tick;
begin
 @(posedge clk); #1;
 if ({v10,h10,s10,v8,h8,s8} !== {2{valid & rstn,hs & rstn,vs & rstn}}) $fatal(1,"sync mismatch");
 if(rstn && valid) begin
  check(r10,expected(r,g,b,1023));check(g10,expected(g,r,b,1023));check(b10,expected(b,r,g,1023));
  check(r8,expected(r[7:0],g[7:0],b[7:0],255));check(g8,expected(g[7:0],r[7:0],b[7:0],255));check(b8,expected(b[7:0],r[7:0],g[7:0],255));
 end else if ({r10,g10,b10,r8,g8,b8} !== 54'd0) $fatal(1,"blank/reset mismatch");
end
endtask
integer i;
integer previous;
initial begin
 tick;
 // First pixel immediately after reset, no ROM warm-up clocks.
 @(negedge clk);rstn=1;valid=1;r=512;g=128;b=64;tick;
 for(i=0;i<1024;i=i+1) begin
  @(negedge clk);r=i;g=1023-i;b=(i*37)%1024;hs=i%2;vs=(i%17)==0;valid=(i%13)!=0;
  tick;
  // Check every input including values that appeared during blanking.
  @(negedge clk);valid=1;tick;
 end
 @(negedge clk);rstn=0;tick;
 @(negedge clk);rstn=1;valid=1;r=0;g=1023;b=512;tick;
 previous=0;
 for(i=0;i<1024;i=i+1) begin
  @(negedge clk);valid=1;r=i;g=i;b=i;tick;
  if(r10!==g10 || g10!==b10 || r10<previous || r10<i) $fatal(1,"neutral ramp failure");
  previous=r10;
 end
 $display("PASS: 8/10-bit display gamma, all levels, independent RGB, immediate startup, blanking, reset and sync");
 $finish;
end
endmodule

