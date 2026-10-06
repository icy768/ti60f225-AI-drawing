`timescale 1ns/1ps
module debayer_tb;
 parameter GAIN_CASE=0;
 reg clk=0,rstn=0,vs=0,hs=0,de=0;
 reg [15:0] raw=0;
 always #5 clk=~clk;
 wire ovs,ohs,ode,valid;
 wire [47:0] rgb;
 debayer_top_2to1 dut(.in_pclk(clk),.in_rstn(rstn),.raw_vs_i(vs),.raw_hs_i(hs),
  .raw_de_i(de),.raw_valid_i(de),.raw_datax4_i(raw),
  .r_gain(16'd256),.g_gain(GAIN_CASE?16'd128:16'd256),.b_gain(GAIN_CASE?16'd384:16'd256),
  .rgb_vs_o(ovs),.rgb_hs_o(ohs),.rgb_de_o(ode),.rgb_valid_o(valid),.rgb_datax2_o(rgb));
 integer x,y,ox=0,oy=0,checked=0;
 reg prev=0;
 always @(negedge clk) if(rstn) begin
   if(prev && !ode) begin oy=oy+1;ox=0;end
   if(ode && valid) begin
     if(oy>=6 && oy<=12 && ox>=5 && ox<=10) begin
       if(rgb!==(GAIN_CASE?48'h3c32c83c32c8:48'h2864c82864c8)) $fatal(1,"BGGR color mismatch row=%0d pair=%0d RGB=%h",oy,ox,rgb);
       checked=checked+1;
     end
     ox=ox+1;
   end
   prev=ode;
 end
 initial begin
   repeat(10) @(negedge clk);rstn=1;
   @(negedge clk);vs=1;repeat(4) @(negedge clk);vs=0;
   repeat(10) @(negedge clk);
   for(y=0;y<18;y=y+1) begin
     hs=1;repeat(4) @(negedge clk);hs=0;
     repeat(4) @(negedge clk);
     for(x=0;x<16;x=x+1) begin
       de=1;raw=y%2?16'hc864:16'h6428;@(negedge clk);
     end
     de=0;raw=0;repeat(12) @(negedge clk);
   end
   repeat(30) @(negedge clk);
   if(checked!=42) $fatal(1,"Missing active pixels checked=%0d",checked);
   $display("PASS BGGR input to RGB output, 84 interior pixels with independent R/G/B levels");
   $finish;
 end
endmodule
