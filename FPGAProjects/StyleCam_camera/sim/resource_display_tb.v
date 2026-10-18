`timescale 1ns/1ps
module tb;
 reg ac=0,pc=0;always #5 ac=~ac;always #3.367 pc=~pc;
 reg rst=1,pub=0,owe=0;reg [1:0] mode=0;reg [10:0] oa=0;reg [7:0] od=0;
 wire [255:0] st,rstt;wire [31:0] aa,ra,raa,rra;wire av,wv,br,arv,rr,rav,rwv,rbr,rarv,rrr;
 wire [127:0] wd,rwd;wire hs,vs,de,rhs,rvs,rde;wire [23:0] rgb,rrgb;
 wire ready,rready,complete,rcomplete,shown,rshown;wire [1:0] bank,rbank;
 reg reading=0;reg [31:0] saved;reg [3:0] beat=0;integer delay=0,cycle=0,frames=0,checks=0,i;
 wire arready=!reading&&cycle%7!=0;
 wire rv=reading&&delay==0;
 wire [31:0] pa=saved+beat*16;
 function [23:0] px(input [31:0] a);begin px={8'(a>>2),8'((a>>5)^a),8'((a>>12)+a)};end endfunction
 wire [127:0] data={8'd0,px(pa+12),8'd0,px(pa+8),8'd0,px(pa+4),8'd0,px(pa)};
`define PORTS \
 .uc(ac),.urst(rst),.ac(ac),.arst(rst),.pc(pc),.prst(rst),.calibrated(1'b1), \
 .pixel(24'd0),.pv(1'b0),.new_frame(1'b0),.original_frame(1'b0),.mode(mode), \
 .write_bank(2'd1),.publish(pub),.publish_bank(2'd0),.publish_orig(2'd2), \
 .osd_we(owe),.osd_addr(oa),.osd_data(od),.awready(1'b0),.wready(1'b0),.bvalid(1'b0),.bresp(2'd0), \
 .arready(arready),.rdata(data),.rvalid(rv),.rlast(beat==15),.rresp(2'd0)
 sc_display dut(`PORTS,.pready(ready),.output_complete(complete),.shown_valid(shown),.shown_bank(bank),.status(st),
 .awaddr(aa),.awvalid(av),.wdata(wd),.wvalid(wv),.bready(br),.araddr(ra),.arvalid(arv),.rready(rr),
 .hs(hs),.vs(vs),.de(de),.red(rgb[23:16]),.green(rgb[15:8]),.blue(rgb[7:0]));
 sc_display_resource2 reference(`PORTS,.pready(rready),.output_complete(rcomplete),.shown_valid(rshown),.shown_bank(rbank),.status(rstt),
 .awaddr(raa),.awvalid(rav),.wdata(rwd),.wvalid(rwv),.bready(rbr),.araddr(rra),.arvalid(rarv),.rready(rrr),
 .hs(rhs),.vs(rvs),.de(rde),.red(rrgb[23:16]),.green(rrgb[15:8]),.blue(rrgb[7:0]));
 always @(posedge ac)begin
  if(rst)begin reading<=0;cycle<=0;delay<=0;beat<=0;end
  else begin
   cycle<=cycle+1;
   if(arv&&arready)begin reading<=1;saved<=ra;beat<=0;delay<=cycle%23+3;end
   if(delay>0)delay<=delay-1;
   if(rv&&rr)begin beat<=beat+1'b1;if(beat==15)reading<=0;end
  end
  #0.01;
  if(!rst&&({ready,complete,shown,bank,st,av,wd,wv,br,arv,rr}!=={rready,rcomplete,rshown,rbank,rstt,rav,rwd,rwv,rbr,rarv,rrr}||
     (arv&&ra!==rra)||(av&&aa!==raa)))
   $fatal(1,"Display AXI/status cycle equivalence failed at %0t addr=%h ref=%h",$time,ra,rra);
 end
 always @(posedge pc)begin
  #0.01;
  if(!rst)begin
   if({hs,vs,de,rgb}!=={rhs,rvs,rde,rrgb})$fatal(1,"HDMI/OSD mismatch x=%0d y=%0d rgb=%h ref=%h",dut.x,dut.y,rgb,rrgb);
   checks=checks+1;
  end
 end
 initial begin
  repeat(20)@(negedge ac);rst=0;
  // Exercise every glyph, transparent code zero and highlight, over the full grid.
  for(i=0;i<2048;i=i+1)begin
   @(negedge ac);owe=1;oa=i;od=(i%101==0)?0:8'((i%96)+32)|((i%2)?8'h80:0);
  end
  @(negedge ac);owe=0;
  force dut.valid_banks=3'b111;force reference.valid_banks=3'b111;
  pub=1;@(negedge ac);pub=0;
  // Start at vblank to avoid spending a whole frame waiting for publication.
  repeat(20)@(negedge pc);
  force dut.x=0;force dut.y=1080;force reference.x=0;force reference.y=1080;
  @(negedge pc);release dut.x;release dut.y;release reference.x;release reference.y;
  for(i=0;i<3;i=i+1)begin
   wait(dut.x==0&&dut.y==0);@(negedge pc);
   // Change the next mode a line before vblank, allowing its CDC to settle.
   wait(dut.x==0&&dut.y==1079);@(negedge pc);
   if(dut.dm!==2'(i))$fatal(1,"Layout coverage failed: got %0d expected %0d",dut.dm,i);
   if(dut.line_base!=640*480*4)$fatal(1,"Did not scan full VGA address range: %0d",dut.line_base);
   mode=(i==0)?1:2;
   wait(dut.y==1081);
  end
  rst=1;repeat(20)@(negedge ac);rst=0;repeat(40)@(negedge pc);
  $display("PASS HDMI/OSD cycle equivalence: all three full VGA layouts, all glyphs/highlights, >1MiB addresses, DDR stalls, reset; %0d pixel clocks",checks);$finish;
 end
 initial begin #80000000;$fatal(1,"Display equivalence timeout");end
endmodule
