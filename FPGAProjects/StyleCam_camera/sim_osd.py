"""OSD layer: pixel-exact check of the 80x23 character grid (8x16 font scaled 3x) over the idle colour bars,
including a run-time character write from the control clock domain."""
from pathlib import Path
import json, os, subprocess
ROOT=Path(__file__).resolve().parent
S=ROOT/'validation/osd';S.mkdir(parents=True,exist_ok=True)
BIN=Path(os.environ.get('ICARUS_BIN',ROOT.parent/'tools/iverilog/mingw64/bin'))
font=[int(v,16) for v in (ROOT/'model/font8x16.mem').read_text().split()]
text=[0]*2048
for i,ch in enumerate('Ag'):text[2*80+3+i]=ord(ch)
text[2*80+10]=ord('#')|0x80
(S/'text.mem').write_text('\n'.join(f'{v:02x}' for v in text)+'\n')
ROWS=range(96,144)    # character row 2
tb=r'''
`timescale 1ns/1ps
module tb;
 reg ac=0,pc=0;always #5 ac=~ac;always #3.367 pc=~pc;reg rst=1;reg we=0;reg [10:0] wa=0;reg [7:0] wd=0;
 wire hs,vs,de;wire [7:0] r,g,b;integer f,ex,ey;
 sc_display #(.IW(640),.IH(32),.TEXT("validation/osd/text.mem")) dut(.uc(ac),.urst(rst),.ac(ac),.arst(rst),.pc(pc),.prst(rst),.calibrated(1'b1),
 .pixel(24'd0),.pv(1'b0),.pready(),.new_frame(1'b0),.original_frame(1'b0),.mode(2'd1),.status(),
 .write_bank(1'b0),.publish(1'b0),.publish_bank(1'b0),.publish_orig(2'd0),.output_complete(),.shown_valid(),.shown_bank(),
 .osd_we(we),.osd_addr(wa),.osd_data(wd),
 .awaddr(),.awvalid(),.awready(1'b0),.wdata(),.wvalid(),.wready(1'b0),.bvalid(1'b0),.bresp(2'd0),.bready(),
 .araddr(),.arvalid(),.arready(1'b0),.rdata(128'd0),.rvalid(1'b0),.rlast(1'b0),.rresp(2'd0),.rready(),
 .hs(hs),.vs(vs),.de(de),.red(r),.green(g),.blue(b));
 always @(negedge pc)if(!rst)begin
  ex=dut.x-4;ey=dut.y;if(ex<0)begin ex=ex+2200;ey=dut.y==0?1124:dut.y-1;end
  if(ey>=96&&ey<144&&ex<960)$fwrite(f,"%0d %0d %02x%02x%02x %0d\n",ex,ey,r,g,b,de);
 end
 initial begin
  f=$fopen("validation/osd/pixels.txt","w");
  repeat(20)@(negedge ac);rst=0;
  // write one more character at row 2, column 12 from the control clock domain
  @(negedge ac);we=1;wa=2*80+12;wd=8'h5a;@(negedge ac);we=0;
  wait(dut.y==150);$fclose(f);$display("DONE");$finish;
 end
endmodule
'''
(S/'tb.v').write_text(tb)
exe=S/'osd.vvp'
subprocess.run([str(BIN/'iverilog.exe'),'-g2012','-s','tb','-o',str(exe),str(S/'tb.v'),str(ROOT/'rtl/sc_display.v'),str(ROOT/'rtl/common.v'),str(ROOT/'rtl/sc_async_fifo.v')],cwd=ROOT,check=True)
r=subprocess.run([str(BIN/'vvp.exe'),str(exe)],cwd=ROOT,capture_output=True,text=True)
assert r.returncode==0 and 'DONE' in r.stdout,r.stdout+r.stderr
text[2*80+12]=0x5a
def bars(x):
    for lim,c in [(240,0xffffff),(480,0xffff00),(720,0x00ffff),(960,0x00ff00)]:
        if x<lim:return c
got={}
for line in (S/'pixels.txt').read_text().split('\n'):
    if line:
        x,y,c,de=line.split();got[int(x),int(y)]=(int(c,16),int(de))
bad=0;glyph_pixels=0
for y in ROWS:
    for x in range(960):
        bg=bars(x);code=text[(y//48)*80+x//24]
        if code==0:want=bg
        else:
            bit=(font[((code&0x7f)-32)*16+(y%48)//3]>>(7-(x%24)//3))&1
            ink=0xffd040 if code&0x80 else 0xffffff
            dim=((bg>>1)&0x7f7f7f)
            want=ink if bit else dim;glyph_pixels+=bit
        c,de=got[x,y]
        if c!=want or de!=1:
            bad+=1
            if bad<5:print('mismatch',x,y,hex(c),hex(want))
assert bad==0 and glyph_pixels>200,(bad,glyph_pixels)
msg=f'PASS OSD: {len(ROWS)*960} pixels exact, {glyph_pixels} glyph pixels, highlight colour, runtime write'
print(msg)
(S/'result.json').write_text(json.dumps(dict(passed=True,message=msg),indent=2))
