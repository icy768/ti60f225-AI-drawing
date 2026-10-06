"""Reproduce the old HDMI shortage and verify deadline arbitration + burst credits."""
from pathlib import Path
import json, subprocess
ROOT=Path(__file__).resolve().parent
S=ROOT/'validation/display_pressure';S.mkdir(exist_ok=True)
BIN=ROOT.parent/'tools/iverilog/mingw64/bin'
before=(ROOT/'rtl/sc_display.v').read_text()
before=before.replace('wire [95:0] rf_data;', 'wire [127:0] rf_data;')
before=before.replace('wire [23:0] selected_pixel=rf_data>>(x[2:1]*24);', 'wire [31:0] selected_pixel=rf_data>>(x[2:1]*32);')
before=before.replace('sc_async_fifo #(.W(96),.AW(9)) display_fifo(ac,arst||flush,compact_read,rf_write,rf_ready,\n  pc,pf_reset,rf_data,rf_valid,rf_take,rf_level);', 'sc_async_fifo #(.W(128),.AW(8)) display_fifo(ac,arst||flush,rdata,rf_write,rf_ready,\n  pc,pf_reset,rf_data,rf_valid,rf_take,);')
before=before.replace('&&rf_level<=496', '')
(S/'before_sc_display.v').write_text(before)
tb=r'''
`timescale 1ns/1ps
module tb;
 reg ac=0,pc=0;always #5 ac=~ac;always #3.367 pc=~pc;
 reg rst=1,pub=0;wire [255:0] status;wire [31:0] da,ma;
 wire dav,dardy,drv,drr,mav,mrr;wire [127:0] data;
 reg reading=0;reg [31:0] addr;reg [3:0] beat;integer delay=0;
 wire mv=reading&&delay==0;wire last=beat==15;
 wire hs,vs,de;wire [7:0] r,g,b;
 function [23:0] pattern(input integer i);begin pattern={8'(i*7+3),8'(i*5+2),8'(i*3+1)};end endfunction
 wire [31:0] ix=(addr-32'h400000)/4+beat*4;
 assign data={8'd0,pattern(ix+3),8'd0,pattern(ix+2),8'd0,pattern(ix+1),8'd0,pattern(ix)};
 sc_display #(.IW(640),.IH(32)) dut(.uc(ac),.urst(rst),.ac(ac),.arst(rst),.pc(pc),.prst(rst),.calibrated(1'b1),
 .pixel(24'd0),.pv(1'b0),.pready(),.new_frame(1'b0),.original_frame(1'b0),.mode(2'd2),.status(status),
 .write_bank(1'b1),.publish(pub),.publish_bank(1'b0),.output_complete(),.shown_valid(),.shown_bank(),
 .awaddr(),.awvalid(),.awready(1'b0),.wdata(),.wvalid(),.wready(1'b0),.bvalid(1'b0),.bresp(2'd0),.bready(),
 .araddr(da),.arvalid(dav),.arready(dardy),.rdata(data),.rvalid(drv),.rlast(last),.rresp(2'd0),.rready(drr),
 .hs(hs),.vs(vs),.de(de),.red(r),.green(g),.blue(b));
 // Permanently queued replay bursts; DDR request latency models shared service.
 sc_read_arbiter #(.DISPLAY_PRIORITY(`PRIORITY)) arb(.clk(ac),.rst(rst),
 .a_addr(da),.a_valid(dav),.a_ready(dardy),.a_rvalid(drv),.a_rready(drr),
 .b_addr(32'd0),.b_valid(1'b1),.b_ready(),.b_rvalid(),.b_rready(1'b1),
 .araddr(ma),.arvalid(mav),.arready(!reading),.rvalid(mv),.rlast(last),.rready(mrr));
 integer replay_bursts=0,display_bursts=0,blocked_display=0;
 always @(posedge ac)begin
  if(rst)begin reading<=0;delay<=0;beat<=0;end
  else begin
   if(mav&&!reading)begin reading<=1;addr<=ma;beat<=0;delay<=90;
    if(ma==0)replay_bursts<=replay_bursts+1;else display_bursts<=display_bursts+1;
   end
   if(delay>0)delay<=delay-1;
   if(mv&&mrr)begin beat<=beat+1'b1;if(last)reading<=0;end
   if(drv&&!drr)blocked_display<=blocked_display+1;
  end
 end
 integer seen=0,mismatches=0,ex,ey,idx;
 always @(negedge pc)begin
  ex=dut.x==0?2199:dut.x-1;ey=dut.x==0?(dut.y==0?1124:dut.y-1):dut.y;
  if(!rst&&ex>=320&&ex<1600&&ey>=60&&ey<124&&dut.image_enable)begin
   idx=((ey-60)/2)*640+(ex-320)/2;
   if({b,g,r}!==pattern(idx))mismatches=mismatches+1;
   if(!de)$fatal(1,"DE alignment");seen=seen+1;
  end
 end
 initial begin
  repeat(20)@(negedge ac);rst=0;force dut.valid_banks=2'b01;
  repeat(10)@(negedge ac);pub=1;@(negedge ac);pub=0;repeat(10)@(negedge pc);
  dut.x=2190;dut.y=1079;
  wait(seen==81920);repeat(10)@(negedge pc);
  if(replay_bursts==0||display_bursts==0)$fatal(1,"No concurrent replay traffic");
  $display("RESULT priority=%0d pixels=%0d mismatches=%0d underflow=%0d display_R_stalls=%0d replay_bursts=%0d",`PRIORITY,seen,mismatches,dut.underflow,blocked_display,replay_bursts);
  if(`PRIORITY&& (mismatches!=0||dut.underflow!=0||blocked_display!=0))$fatal(1,"HDMI pressure test failed");
  if(!`PRIORITY&&dut.underflow==0)$fatal(1,"Baseline did not reproduce shortage");
  if(status[5]!==!`PRIORITY)$fatal(1,"Underflow history flag mismatch");
  rst=1;repeat(20)@(negedge ac);
  if(status[5]!==0)$fatal(1,"Underflow history did not clear on reset");
  $display("PASS");$finish;
 end
 initial begin #10000000;$fatal(1,"Pressure test timeout");end
endmodule
'''
(S/'tb.v').write_text(tb)
results={}
for priority in [0,1]:
 src=ROOT/'rtl/sc_display.v' if priority else S/'before_sc_display.v'
 exe=S/f'pressure_{priority}.vvp'
 subprocess.run([str(BIN/'iverilog.exe'),'-g2012',f'-DPRIORITY={priority}','-s','tb','-o',str(exe),str(S/'tb.v'),str(src),str(ROOT/'rtl/sc_async_fifo.v'),str(ROOT/'rtl/sc_read_arbiter.v')],check=True)
 run=subprocess.run([str(BIN/'vvp.exe'),str(exe)],capture_output=True,text=True,encoding='utf-8',errors='replace')
 (S/f'pressure_{priority}.log').write_text(run.stdout+run.stderr,encoding='utf-8');print(run.stdout,flush=True)
 assert run.returncode==0 and 'PASS' in run.stdout,run.stdout+run.stderr
 results[str(priority)]={'passed':True,'log':run.stdout}
(S/'result.json').write_text(json.dumps({'passed':True,'baseline_underflow_reproduced':True,'fixed_pixels_exact':81920,'fixed_underflow':0,'fixed_R_backpressure':0,'concurrent_replay':True,'underflow_history_and_reset':True,'tests':results},indent=2),encoding='utf-8')
