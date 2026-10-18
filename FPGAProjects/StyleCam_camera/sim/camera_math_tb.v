`timescale 1ns/1ps
module tb;
 reg clk=0;always #5 clk=~clk;
 reg signed [13:0] numerator=0;
 integer i,want;
 sc_camera_rgb dut(.clk(clk),.rst(1'b1),.vs(1'b0),.valid(1'b0),.raw(40'd0),
  .rgb_r_gain(16'd256),.rgb_g_gain(16'd256),.rgb_b_gain(16'd256),.rgb_request(1'b0),.ae_ack(1'b0));
 initial begin
  force dut.mhc[0].value_a=numerator;
  for(i=-8192;i<8192;i=i+1)begin
   numerator=i;#1;want=i<0?0:(i>=4080?255:(i>>4));
   if(dut.mhc[0].ca!==want[7:0])$fatal(1,"clip input %0d",i);
  end
  for(i=0;i<1024;i=i+1)begin
   want=(i>>2)>16?(i>>2)-16:0;
   if(dut.black(i[9:0])!==want[7:0])$fatal(1,"black input %0d",i);
  end
  $display("PASS exact camera arithmetic: all 16384 signed clip inputs and 1024 RAW black-level inputs");
  $finish;
 end
endmodule
