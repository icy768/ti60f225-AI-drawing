// Style blend in sc_in_refresh: the blending DUT (original constants, blend_style/blend_alpha)
// must write exactly the coefficients of the unmodified reference module given constants in which
// style STYLE was replaced by the integer blend A + floor((B-A)*a/8) (sim_in_blend.py).
`timescale 1ns/1ps
module in_blend_tb #(parameter STYLE=0,BSTYLE=1,ALPHA=4,REFFILE="ref.mem",STATS="stats.hex");
 reg clk=0,rst=1,start=0;reg [3:0] layer=0;always #3.333 clk=~clk;
 reg [99:0] stats[0:12*24-1];initial $readmemh(STATS,stats);
 wire [7:0] di,ri;wire dbusy,ddone,derr,rbusy,rdone,rerr,dwe,rwe;
 wire [4:0] dl,rl;wire [11:0] da,ra;wire [37:0] dd,rd;
 wire [99:0] ds=stats[layer*24+di],rs=stats[layer*24+ri];
 sc_in_refresh #(.WIDTH(640),.HEIGHT(480),.CONSTFILE("model/in_constants.mem"),.TRACE(0)) dut(
  .clk(clk),.rst(rst),.start(start),.style(STYLE[1:0]),.layer(layer),.blend_style(BSTYLE[1:0]),.blend_alpha(ALPHA[3:0]),
  .busy(dbusy),.done(ddone),.error(derr),.stats_index(di),.stats_s1(ds[99:60]),.stats_s2(ds[59:0]),
  .cfg_we(dwe),.cfg_layer(dl),.cfg_addr(da),.cfg_data(dd),.trace_index(10'd0),.trace_data(),.cycles(),.writes());
 sc_in_refresh_ref #(.WIDTH(640),.HEIGHT(480),.CONSTFILE(REFFILE),.TRACE(0)) ref_unit(
  .clk(clk),.rst(rst),.start(start),.style(STYLE[1:0]),.layer(layer),
  .busy(rbusy),.done(rdone),.error(rerr),.stats_index(ri),.stats_s1(rs[99:60]),.stats_s2(rs[59:0]),
  .cfg_we(rwe),.cfg_layer(rl),.cfg_addr(ra),.cfg_data(rd),.trace_index(10'd0),.trace_data(),.cycles(),.writes());
 reg [54:0] dw[0:31],rw[0:31];integer nd=0,nr=0,k,bad=0,total=0,dcyc,rcyc,gotd,gotr;
 always @(posedge clk)begin
  if(dwe)begin dw[nd]={dl,da,dd};nd=nd+1;end
  if(rwe)begin rw[nr]={rl,ra,rd};nr=nr+1;end
 end
 integer L;
 initial begin
  repeat(10)@(posedge clk);rst=0;repeat(5)@(posedge clk);
  for(L=0;L<12;L=L+1)begin
   nd=0;nr=0;layer=L;gotd=0;gotr=0;dcyc=0;
   @(negedge clk);start=1;@(negedge clk);start=0;
   while(!(gotd&&gotr))begin @(posedge clk);if(ddone)gotd=1;if(rdone)gotr=1;dcyc=dcyc+1;end
   repeat(4)@(posedge clk);
   if(derr||rerr)begin $display("FAIL error flag layer %0d dut=%0d ref=%0d",L,derr,rerr);bad=bad+1;end
   if(nd!=nr||nd!=((L==0||L==11)?16:24))begin $display("FAIL write count layer %0d dut=%0d ref=%0d",L,nd,nr);bad=bad+1;end
   for(k=0;k<nd&&k<nr;k=k+1)if(dw[k]!==rw[k])begin
    if(bad<6)$display("FAIL layer %0d write %0d dut=%h ref=%h",L,k,dw[k],rw[k]);bad=bad+1;
   end
   total=total+nd;
  end
  if(bad==0)$display("PASS style=%0d blend=%0d alpha=%0d coefficients=%0d",STYLE,BSTYLE,ALPHA,total);
  else $fatal(1,"FAIL %0d mismatches",bad);
  $finish;
 end
 initial begin #50000000;$fatal(1,"timeout");end
endmodule
