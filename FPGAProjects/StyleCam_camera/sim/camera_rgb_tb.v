module tb;
 reg clk=0;always #10 clk=~clk;reg rst=1,vs=0,valid=0;reg [39:0] raw=0;
 wire [47:0] rgb;wire v,sof,eof;wire [31:0] frames,errors;
 reg [47:0] expected[0:47];integer count=0,f,y,x,k;
 sc_camera_rgb #(.IW(24),.IH(20),.OW(8),.OH(6)) dut(clk,rst,vs,valid,raw,rgb,v,sof,eof,frames,errors);
 function [9:0] sample(input integer frame,input integer xx,input integer yy);
  sample=((frame*31+(23-xx)*7+yy*11)%240+16)*4;
 endfunction
 always @(posedge clk)if(v)begin
  if(rgb!==expected[count])$fatal(1,"RGB pair %0d actual %h expected %h",count,rgb,expected[count]);
  if(sof!==(count%24==0)||eof!==(count%24==23))$fatal(1,"RGB frame markers");
  count=count+1;
 end
 initial begin
  $readmemh("validation/camera_sim/rgb_expected.hex",expected);
  repeat(5)@(negedge clk);rst=0;
  for(f=0;f<2;f=f+1)begin
   vs=1;repeat(3)@(negedge clk);vs=0;repeat(3)@(negedge clk);
   for(y=0;y<20;y=y+1)begin
    for(x=0;x<24;x=x+4)begin
     valid=1;for(k=0;k<4;k=k+1)raw[k*10+:10]=sample(f,x+k,y);@(negedge clk);
     if(x%12==0)begin valid=0;repeat(2)@(negedge clk);end
    end
    valid=0;repeat(7)@(negedge clk);
   end
  end
  repeat(30)@(negedge clk);
  if(count!=48||frames!=2||errors!=0)$fatal(1,"preprocessor counts %0d frames %0d errors %0d",count,frames,errors);
  rst=1;repeat(3)@(negedge clk);if(v||frames||errors)$fatal(1,"camera reset");
  $display("PASS camera RGB: 96 pixels, horizontal mirror/GBRG crop, black level, Gamma, gaps, frame markers, reset");$finish;
 end
 initial begin #1000000;$fatal(1,"preprocessor timeout");end
endmodule
