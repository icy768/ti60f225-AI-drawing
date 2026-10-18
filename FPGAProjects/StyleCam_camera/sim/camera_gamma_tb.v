`timescale 1ns/1ps
// Exhaust all 256 linear inputs through all twelve registered Gamma paths.
module tb;
 reg clk=0; always #5 clk=~clk;
 reg [7:0] stimulus=0;
 wire [7:0] reverse=255-stimulus, alternate=stimulus^8'haa;
 reg [9:0] reference[0:1023];
 integer n;
 sc_camera_rgb dut(.clk(clk),.rst(1'b0),.vs(1'b0),.valid(1'b0),.raw(40'd0),
  .rgb_r_gain(16'd256),.rgb_g_gain(16'd256),.rgb_b_gain(16'd256),
  .rgb_request(1'b0),.ae_ack(1'b0));
 initial begin
  $readmemh("model/camera_gamma.mem",reference);
  force dut.v3=1'b1;
  for(n=0;n<256;n=n+1) begin
   @(negedge clk);stimulus=n;
   @(posedge clk);#2;
  end
  $display("PASS Gamma: 256 inputs x 12 paths exactly match unchanged 1024-entry curve");
  $finish;
 end
 genvar p;
 generate for(p=0;p<4;p=p+1)begin:check_path
  initial begin
   force dut.mhc[p].linear_r=stimulus;
   force dut.mhc[p].linear_g=reverse;
   force dut.mhc[p].linear_b=alternate;
  end
  always @(posedge clk)begin
   #1;
   if(dut.enc_r[p] !== (reference[{stimulus,stimulus[7:6]}]>>2) ||
      dut.enc_g[p] !== (reference[{reverse,reverse[7:6]}]>>2) ||
      dut.enc_b[p] !== (reference[{alternate,alternate[7:6]}]>>2))
    $fatal(1,"Gamma mismatch pixel %0d input %0d",p,stimulus);
  end
 end endgenerate
endmodule
