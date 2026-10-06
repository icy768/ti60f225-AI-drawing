`timescale 1ns/1ps
module black_level_tb;
 reg [31:0] pixels;
 wire [31:0] corrected,bypass,all_black;
 raw_black_level #(.BLACK_LEVEL(8'd16)) dut(.raw_pixels(pixels),.corrected_pixels(corrected));
 raw_black_level #(.BLACK_LEVEL(8'd0)) zero(.raw_pixels(pixels),.corrected_pixels(bypass));
 raw_black_level #(.BLACK_LEVEL(8'd255)) full(.raw_pixels(pixels),.corrected_pixels(all_black));
 integer i,p,v,expected;
 initial begin
   for(i=0;i<256;i=i+1) begin
     // Distinct sequences exercise every input value in every packed pixel position.
     for(p=0;p<4;p=p+1) pixels[p*8 +: 8]=(i+p*67)%256;
     #1;
     for(p=0;p<4;p=p+1) begin
       v=(i+p*67)%256;expected=v<16?0:v-16;
       if(corrected[p*8 +: 8]!==expected[7:0]) $fatal(1,"BLC wraparound/order value=%0d pixel=%0d",v,p);
     end
     if(bypass!==pixels || all_black!==0) $fatal(1,"BLC endpoint parameter failure");
   end
   pixels=32'h1210100f;#1;
   if(corrected!==32'h02000000) $fatal(1,"Measured dark range did not clamp near zero");
   $display("PASS RAW8 BLC all levels/all four pixels, no wraparound, zero/max parameters, measured dark codes");
   $finish;
 end
endmodule
