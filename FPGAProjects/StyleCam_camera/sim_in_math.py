"""Check actual RTL sqrt/division/IN against model statistics and integer oracle."""
from pathlib import Path
import subprocess,json,math
import numpy as np
from PIL import Image
from reference import ROOT,load,run
import sys
sys.path.insert(0,str(ROOT.parent/'StyleCam/algo'))
import golden,torch
torch.set_num_threads(2)
def round_div(a,b):
    sign=-1 if (a<0)!=(b<0) else 1
    quotient,remainder=divmod(abs(int(a)),abs(int(b)))
    denominator=abs(int(b))
    return sign*(quotient+int(2*remainder>denominator or (2*remainder==denominator and quotient%2)))
S=ROOT/'validation/in_math';S.mkdir(parents=True,exist_ok=True)
q=load();rng=np.random.default_rng(43);vectors=[];cases=[]
def oracle(a,b,n,s,g,beta,eps):
    root=math.isqrt((max(b*n-a*a,0)<<80)+eps)
    gain=round_div(g,root)
    m=max(-131072,min(131071,round_div(gain,2**(40-s))))
    bias=max(-524288,min(524287,round_div(beta-round_div(gain*a*256,n),2**40)+128))
    return ((m&0x3ffff)<<20)|(bias&0xfffff)
def add(a,b,n,s,g,beta,eps,expected=None):
    values=[(a,40),(b,60),(n,19),(s,5),(g,112),(beta,56),(eps,136),(oracle(a,b,n,s,g,beta,eps),38)]
    if expected is not None:assert values[-1][0]==expected
    word=0
    for v,w in values:word=(word<<w)|(v&((1<<w)-1))
    vectors.append(word)
images=[('room',np.array(Image.open(ROOT.parent/'StyleCam/data/val2017/000000000139.jpg').convert('RGB').resize((640,480)))),
('random32',rng.integers(0,256,(24,32,3),dtype=np.uint8)),('black32',np.zeros((24,32,3),dtype=np.uint8)),('white32',np.full((24,32,3),255,dtype=np.uint8))]
for name,im in images:
    for style in range(3):
        official=golden.load(str(ROOT/'model/qparams'))
        _,stats,dumps=golden.run(official,im,style,dump=True);coeff=[(d['M'],d['B']) for d in dumps];begin=len(vectors)
        print('Generated official V21 IN statistics:',name,style,flush=True)
        for L,st,(M,B) in zip(q['layers'],stats,coeff):
            if 'gamma' not in L:continue
            s1,s2,n=st
            for c in range(L['cout']):
                k=float(L['s_x']*L['s_w'][c])*(2**L['R'])
                g=round(float(L['gamma'][style,c])/float(L['s_y'])*2**40)*n*2**40
                beta=round(float(L['beta'][style,c])/float(L['s_y'])*256*2**40)
                eps=round(float(L['eps'])/(k*k)*n*n*2**80)
                add(int(s1[c]),int(s2[c]),n,L['S'],g,beta,eps,((int(M[c])&0x3ffff)<<20)|(int(B[c])&0xfffff))
        cases.append(dict(image=name,style=style,channels=len(vectors)-begin))
for a in (-262144,0,262143):
    for g in (-2**100,0,2**100):add(a,a*a,1,23,g,0,2**80)
(S/'vectors.hex').write_text('\n'.join(f'{x:0142x}' for x in vectors),encoding='ascii')
tb=r'''
module tb;
 reg clk=0;always #5 clk=~clk;reg rst=1,start=0;
 reg [565:0] vec[0:COUNT-1];integer i,cycles=0,maxcycles=0,k;
 reg signed[39:0] s1;reg[59:0] s2;reg[18:0] n;reg[4:0] s;
 reg signed[111:0] g;reg signed[55:0] beta;reg[135:0] eps;reg[37:0] expected;
 wire busy,done,error;wire[37:0] coefficient;
 sc_in_math dut(clk,rst,start,s1,s2,n,s,g,beta,eps,busy,done,error,coefficient);
 initial begin
  $readmemh("validation/in_math/vectors.hex",vec);repeat(3)@(negedge clk);rst=0;
  for(i=0;i<COUNT;i=i+1)begin
   {s1,s2,n,s,g,beta,eps,expected}=vec[i];start=1;@(negedge clk);start=0;cycles=0;
   while(!done)begin @(negedge clk);cycles=cycles+1;if(cycles>2500)$fatal(1,"math timeout");end
   if(error||coefficient!==expected)$fatal(1,"IN mismatch vector %0d actual=%h expected=%h s1=%d",i,coefficient,expected,s1);
   if(cycles>maxcycles)maxcycles=cycles;
   @(negedge clk);
   if(i%272==271)$display("Checked %0d coefficients",i+1);
  end
  n=0;start=1;@(negedge clk);start=0;
  if(!done||!error||busy)$fatal(1,"zero N rejection");@(negedge clk);
  n=76800;start=1;@(negedge clk);start=0;repeat(30)@(negedge clk);rst=1;@(negedge clk);
  if(busy||done)$fatal(1,"reset during arithmetic");rst=0;@(negedge clk);
  $display("PASS IN math %0d vectors max_cycles=%0d zero_N reset",COUNT,maxcycles);$finish;
 end
endmodule
'''.replace('COUNT',str(len(vectors)))
(S/'tb.v').write_text(tb,encoding='ascii')
bin=ROOT.parent/'tools/iverilog/mingw64/bin'
subprocess.run([str(bin/'iverilog.exe'),'-g2012','-s','tb','-o',str(S/'test.vvp'),'rtl/sc_in_alu.v','rtl/sc_in_math.v',str(S/'tb.v')],cwd=ROOT,check=True)
with (S/'simulation.log').open('wb') as f:res=subprocess.run([str(bin/'vvp.exe'),str(S/'test.vvp')],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
log=(S/'simulation.log').read_text(errors='replace');print(log,flush=True)
assert res.returncode==0 and 'PASS IN math' in log
report=dict(passed=True,RTL=True,network='v21b_ukiyoe_qat900_640x480',official_golden_statistics=True,VGA_statistics_included=True,vectors=len(vectors),model_coefficients_exact=True,cases=cases,corner_cases=9,zero_N_rejected=True,reset_during_arithmetic=True)
(S/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
