"""Exercise the actual VGA ROM reader and coefficient writes across every bank."""
from pathlib import Path
import hashlib,json,math,subprocess
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'validation/serial_constants_rtl';OUT.mkdir(parents=True,exist_ok=True)
words=[int(x,16) for x in (ROOT/'model/in_constants.mem').read_text().split()]
def signed(v,w):return v-(1<<w) if v&(1<<(w-1)) else v
def rne(v,d):
    q,r=divmod(abs(v),d)
    q+=2*r>d or (2*r==d and q&1)
    return -q if v<0 else q
shifts=[20,21,17,17,19,17,18,17,19,18,20,19]
expected=[];original=[]
for st in range(3):
    for layer in range(12):
        for c in range(16 if layer in (0,11) else 24):
            w=words[st*288+layer*24+c];original.append(w)
            g=signed(w>>192,112);b=signed((w>>136)&((1<<56)-1),56)
            eps=w&((1<<136)-1)
            m=max(-131072,min(131071,rne(rne(g,math.isqrt(eps)),1<<(40-shifts[layer]))))
            bias=max(-524288,min(524287,rne(b,1<<40)+128))
            expected.append(((m&0x3ffff)<<20)|(bias&0xfffff))
(OUT/'words.hex').write_text('\n'.join(f'{x:076x}' for x in original),encoding='ascii')
(OUT/'coeff.hex').write_text('\n'.join(f'{x:010x}' for x in expected),encoding='ascii')
tb=r'''
`timescale 1ns/1ps
module tb;
 reg clk=0;always #5 clk=~clk;reg rst=1,start=0;reg[1:0] style=0;reg[3:0] layer=0;
 wire busy,done,error,cw;wire[7:0] idx;wire[4:0] cl;wire[11:0] ca;wire[37:0] cd;
 reg[303:0] words[0:815];reg[37:0] coeff[0:815];integer n=0,reads=0,l,s,cycles,base;
 sc_in_refresh #(.TRACE(0)) dut(clk,rst,start,style,layer,busy,done,error,idx,40'd0,60'd0,
  cw,cl,ca,cd,10'd0,, ,);
 always @(posedge clk)if(!rst)begin
  if(dut.math_start)begin
   if(dut.word!==words[reads])$fatal(1,"VGA ROM word %0d",reads);
   reads=reads+1;
  end
  if(cw)begin
   if(cd!==coeff[n])$fatal(1,"VGA coefficient %0d actual=%h expected=%h",n,cd,coeff[n]);
   if(cl!=layer||ca!=style*((layer==0||layer==11)?16:24)+(n-base))$fatal(1,"cfg address");
   n=n+1;
  end
 end
 initial begin
  $readmemh("validation/serial_constants_rtl/words.hex",words);
  $readmemh("validation/serial_constants_rtl/coeff.hex",coeff);
  repeat(4)@(negedge clk);rst=0;
  for(s=0;s<3;s=s+1)for(l=0;l<12;l=l+1)begin
   style=s;layer=l;base=n;start=1;@(negedge clk);start=0;cycles=0;
   while(!done)begin @(negedge clk);cycles=cycles+1;if(cycles>200000)$fatal(1,"ROM reader timeout");end
   if(error||n-base!=((l==0||l==11)?16:24))$fatal(1,"layer result");
   @(negedge clk);
  end
  if(n!=816||reads!=816)$fatal(1,"count");
  $display("PASS VGA serial ROM: 816 exact words and coefficients across all 13 banks");$finish;
 end
endmodule
'''
(OUT/'tb.v').write_text(tb,encoding='ascii')
BIN=ROOT.parent/'tools/iverilog/mingw64/bin'
files=['sc_in_refresh.v','sc_in_math.v','sc_in_alu.v']
exe=OUT/'test.vvp'
subprocess.run([str(BIN/'iverilog.exe'),'-g2012','-s','tb','-o',str(exe),str(OUT/'tb.v'),
                *[str(ROOT/'rtl'/f) for f in files]],cwd=ROOT,check=True)
with (OUT/'simulation.log').open('w') as log:
    result=subprocess.run([str(BIN/'vvp.exe'),str(exe)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
log=(OUT/'simulation.log').read_text();print(log)
assert result.returncode==0 and 'PASS VGA serial ROM' in log
(OUT/'result.json').write_text(json.dumps(dict(passed=True,vga_words_exact=816,coefficients_exact=816,
    source_sha256={f:hashlib.sha256((ROOT/'rtl'/f).read_bytes()).hexdigest() for f in files}),indent=2),encoding='utf-8')
