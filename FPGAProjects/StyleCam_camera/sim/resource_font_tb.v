`timescale 1ns/1ps
module tb;
 reg clk=0;always #5 clk=~clk;
 reg [6:0] glyph=0;reg [3:0] row=0;wire [7:0] data;
 reg [7:0] original[0:1535],expected1,expected2;
 integer cycles=0,i,seed=74631;
 sc_osd_font dut(clk,glyph,row,data);
 always @(posedge clk)begin
  expected1<=original[{glyph,row}];expected2<=expected1;
  cycles=cycles+1;#0.01;
  if(cycles>2&&data!==expected2)$fatal(1,"Font byte/latency mismatch cycle=%0d got=%h expected=%h",cycles,data,expected2);
 end
 initial begin
  $readmemh("model/font8x16.mem",original);
  for(i=0;i<1536;i=i+1)begin @(negedge clk);glyph=i/16;row=i%16;end
  for(i=0;i<5000;i=i+1)begin @(negedge clk);glyph=$unsigned($random(seed))%96;row=$random(seed);end
  repeat(3)@(negedge clk);
  $display("PASS all 96 glyphs x 16 rows and 5000 random transitions, exact two-stage font latency");$finish;
 end
endmodule
`include "rtl/sc_osd_font.vh"
