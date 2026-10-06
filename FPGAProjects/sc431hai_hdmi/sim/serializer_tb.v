`timescale 1ns/1ps
module serializer_tb;
 reg fast=0,slow=0,vs=0,hs=0,de=0;
 reg [47:0] pixels=0;
 always #5 fast=~fast;
 // Related clocks with coincident rising edges, as configured by the same PLL.
 always @(posedge fast) slow<=~slow;
 wire ovs,ohs,ode;
 wire [23:0] rgb;
 serializer_under_test dut(.hdmi_tx_slow_clk(fast),.rgb_vs(vs),.rgb_hs(hs),.rgb_de(de),
  .rgb_datax2(pixels),.hdmi_tx_vs(ovs),.hdmi_tx_hs(ohs),.hdmi_tx_de(ode),.rgb(rgb));
 function [23:0] pixel;
 input integer x,y;
 begin pixel={8'((x*3+y*19)%256),8'((x*11+y*7)%256),8'((x+y*31)%256)};end
 endfunction
 integer x,y,ox=0,oy=0,count=0;
 reg prev=0;
 always @(negedge fast) begin
   if(prev && !ode) begin
     if(ox!=1920) $fatal(1,"Wrong row length %0d",ox);
     ox=0;oy=oy+1;
   end
   if(ode) begin
     if(rgb!==pixel(ox,oy)) $fatal(1,"Serialization row=%0d x=%0d got=%h expected=%h",oy,ox,rgb,pixel(ox,oy));
     ox=ox+1;count=count+1;
   end
   prev=ode;
 end
 initial begin
   repeat(8) @(posedge slow);vs<=1;
   repeat(5) @(posedge slow);vs<=0;
   repeat(10) @(posedge slow);
   for(y=0;y<12;y=y+1) begin
     hs<=1;repeat(22) @(posedge slow);hs<=0;repeat(74) @(posedge slow);
     for(x=0;x<1920;x=x+2) begin
       de<=1;pixels<={pixel(x+1,y),pixel(x,y)};@(posedge slow);
     end
     de<=0;repeat(44) @(posedge slow);
   end
   repeat(8) @(posedge slow);
   if(count!=1920*12 || oy!=12) $fatal(1,"Missing frame pixels %0d rows %0d",count,oy);
   $display("PASS current top-level HDMI serializer, 23040 changing pixels, even/odd order and all row boundaries");$finish;
 end
 initial begin #1000000;$fatal(1,"Timeout");end
endmodule
