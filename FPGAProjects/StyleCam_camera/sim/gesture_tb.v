// sc_gesture testbench: synthetic 640x480 frames with a moving skin-coloured blob.
//   frame 1: blob at x 100..159, y 100..259 (appears -> every blob pixel "moves")
//   frame 2: blob at x 200..259, y 100..259
// Hand pixels are the blob OUTLINE (skin + intensity edge): top edge (y=100, 60 px,
// differs from the background line above) plus left edge (x=blob_x0, y=101..259, 159 px,
// differs from the background pixel on the left) = 219 per frame.
// Frame 2 expected after eof: o_frames=2, o_count=219,
//   cx = (13770 + 31800) / 219 = 208,   cy = (6000 + 28620) / 219 = 158,
//   grid cell 1 = 119 (top 60 + left-edge y101..159), grid cell 5 = 100, cell 0 = 0.
`timescale 1ns/1ps
module gesture_tb;
 reg cc=0,crst=1;reg [47:0] rgb=0;reg cv=0,sof=0,eof=0;
 wire [31:0] o_frames,o_count,o_sx,o_sy;wire [191:0] o_grid;
 // {motion=24, rb=20, rg=15, rmin=95} - the firmware defaults
 sc_gesture dut(.cc(cc),.crst(crst),.rgb(rgb),.cv(cv),.sof(sof),.eof(eof),
  .cfg(32'h1814_0F5F),.o_frames(o_frames),.o_count(o_count),.o_sx(o_sx),.o_sy(o_sy),
  .o_grid(o_grid));
 always #5 cc=~cc;

 integer fr,bx2,fy;integer blob_x0;integer errors=0;
 // background r=g=b=100 (not skin); blob r=200,g=140,b=90 (skin, and g differs by 40)
 function [7:0] pix_r(input integer x); pix_r=(x>=blob_x0&&x<blob_x0+60&&fy>=100&&fy<260)?200:100; endfunction
 function [7:0] pix_g(input integer x); pix_g=(x>=blob_x0&&x<blob_x0+60&&fy>=100&&fy<260)?140:100; endfunction
 function [7:0] pix_b(input integer x); pix_b=(x>=blob_x0&&x<blob_x0+60&&fy>=100&&fy<260)?90:100; endfunction

 task beat(input integer b);begin
  rgb={pix_b(2*b+1),pix_g(2*b+1),pix_r(2*b+1),pix_b(2*b),pix_g(2*b),pix_r(2*b)};
  cv=1;sof=(b==0&&fy==0);eof=(b==319&&fy==479);
  @(posedge cc);#1;cv=0;sof=0;eof=0;
  @(posedge cc);#1;             // one idle cycle per beat is plenty for the pipeline
 end endtask

 task check32(input [31:0] got,exp,input [127:0] name);begin
  if(got!==exp)begin errors=errors+1;$display("FAIL %0s: got %0d exp %0d",name,got,exp);end
  else $display("ok   %0s = %0d",name,got);
 end endtask

 integer cx,cy;
 initial begin
  repeat(4)@(posedge cc);crst=0;@(posedge cc);#1;
  for(fr=0;fr<2;fr=fr+1)begin
   blob_x0=fr==0?100:200;
   for(fy=0;fy<480;fy=fy+1)
    for(bx2=0;bx2<320;bx2=bx2+1)beat(bx2);
  end
  $display("frames=%0d count=%0d sx=%0d sy=%0d",o_frames,o_count,o_sx,o_sy);
  cx=o_count?o_sx/o_count:0;cy=o_count?o_sy/o_count:0;
  check32(o_frames,2,"frames");
  check32(o_count,219,"count");
  check32(cx,208,"centroid x");check32(cy,158,"centroid y");
  check32(o_grid[1*16+:16],119,"grid cell 1");
  check32(o_grid[5*16+:16],100,"grid cell 5");
  check32(o_grid[0*16+:16],0,"grid cell 0");
  if(errors)$display("gesture_tb FAIL (%0d)",errors);
  else $display("gesture_tb PASS");
  $finish;
 end
endmodule
