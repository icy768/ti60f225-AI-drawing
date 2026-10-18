"""Independent integer-oracle and frozen-RTL tests for the resource IN ALU."""
from pathlib import Path
import hashlib,json,math,os,random,subprocess,sys

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'validation/in_resource_20261017/simulation';OUT.mkdir(parents=True,exist_ok=True)
BIN=Path(os.environ.get('ICARUS_BIN',ROOT.parent/'tools/iverilog/mingw64/bin'))
ALU=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else ROOT/'rtl/sc_in_alu.v'
def rne(a,b):
 q,r=divmod(a,b);return q+int(2*r>b or (2*r==b and q&1))
results={}
for width,word in [(8,4),(16,8),(160,16)]:
 rng=random.Random(9417+width);mask=(1<<width)-1;vectors=[]
 def add(op,a,b):
  a&=mask;b&=mask;borrow=0;error=0
  if op==0:value=a*b
  elif op==1:value=rne(a,b) if b else 0;error=int(b==0)
  elif op==2:value=math.isqrt(a)
  elif op==3:value=a+b
  elif op==4:value=a-b;borrow=int(a<b)
  elif op==5:value=rne(a,1<<(b&255))
  else:value=0;error=1
  v=op
  for x,n in [(a,width),(b,width),(value&mask,width),(borrow,1),(error,1)]:v=(v<<n)|x
  vectors.append(v)
 if width==8:
  for a in range(256):
   for b in range(256):
    for op in [0,1,3,4]:add(op,a,b)
   for b in [0,1,2,7,8,9,16,255]:add(5,a,b)
 if width in [8,16]:
  for a in range(1<<width):add(2,a,0)
 for i in range(600 if width==160 else 200):
  a=rng.getrandbits(width);b=rng.getrandbits(width)
  for op in range(6):add(op,a,b if op!=5 else rng.randrange(256))
 edges=[0,1,2,3,mask,mask-1,1<<(width-1),(1<<(width-1))-1]
 for a in edges:
  for b in edges:
   for op in range(8):add(op,a,b)
 path=OUT/f'alu{width}.hex';digits=(3*width+5+3)//4
 path.write_text('\n'.join(f'{v:0{digits}x}' for v in vectors)+'\n')
 tb=r'''
`timescale 1ns/1ps
module tb;
 localparam W=WIDTH,N=COUNT;
 reg clk=0;always #5 clk=~clk;reg rst=1,start=0;reg [2:0] op;reg [W-1:0] a,b;
 wire busy,done,error,borrow,rb,rd,re,rr;wire [W-1:0] result,ref_result;
 sc_in_alu #(.W(W),.WORD(WORDSIZE)) dut(clk,rst,start,op,a,b,busy,done,error,result,borrow);
 sc_in_alu_resource3 #(.W(W),.WORD(WORDSIZE)) reference(clk,rst,start,op,a,b,rb,rd,re,ref_result,rr);
 reg [3*W+4:0] vectors[0:N-1];reg [W-1:0] expected;reg eb,ee,seen,seen_ref;
 integer i,cycles,max_cycles=0,max_ref=0,current_ref,total_cycles=0,total_ref=0;
 initial begin
  $readmemh("VECTORS",vectors);repeat(3)@(negedge clk);rst=0;
  for(i=0;i<N;i=i+1)begin
   {op,a,b,expected,eb,ee}=vectors[i];start=1;@(negedge clk);start=0;
   seen=0;seen_ref=0;cycles=0;current_ref=0;
   while(!seen||!seen_ref)begin
    if(done&&!seen)begin
     if(error!==ee||(!ee&&(result!==expected||borrow!==eb)))$fatal(1,"New ALU W=%0d vector=%0d op=%0d a=%h b=%h got=%h expected=%h borrow=%b/%b error=%b/%b",W,i,op,a,b,result,expected,borrow,eb,error,ee);
     seen=1;total_cycles=total_cycles+cycles;if(cycles>max_cycles)max_cycles=cycles;
    end
    if(rd&&!seen_ref)begin
     if(re!==ee||(!ee&&(ref_result!==expected||rr!==eb)))$fatal(1,"Reference ALU W=%0d vector=%0d op=%0d",W,i,op);
     seen_ref=1;total_ref=total_ref+cycles;if(cycles>max_ref)max_ref=cycles;
    end
    @(negedge clk);cycles=cycles+1;if(cycles>10000)$fatal(1,"ALU timeout");
   end
   @(negedge clk);
  end
  op=1;a={W{1'b1}};b=3;start=1;@(negedge clk);start=0;
  repeat(2)@(negedge clk);rst=1;@(negedge clk);
  if(busy||done||result!==0)$fatal(1,"ALU reset");rst=0;
  $display("PASS ALU W=%0d vectors=%0d max_cycles=%0d reference_max=%0d total_cycles=%0d reference_total=%0d reset",W,N,max_cycles,max_ref,total_cycles,total_ref);$finish;
 end
endmodule
'''.replace('WIDTH',str(width)).replace('WORDSIZE',str(word)).replace('COUNT',str(len(vectors))).replace('VECTORS',path.relative_to(ROOT).as_posix())
 tbfile=OUT/f'alu{width}_tb.v';tbfile.write_text(tb)
 exe=OUT/f'alu{width}.vvp'
 sources=[ALU,ROOT/'sim/reference/sc_in_alu_resource3.v',tbfile]
 subprocess.run([str(BIN/'iverilog.exe'),'-g2012','-s','tb','-o',str(exe),*[str(s) for s in sources]],cwd=ROOT,check=True)
 proc=subprocess.run([str(BIN/'vvp.exe'),str(exe)],cwd=ROOT,capture_output=True,text=True,errors='replace')
 log=proc.stdout+proc.stderr;(OUT/f'alu{width}.log').write_text(log);print(log,flush=True)
 assert proc.returncode==0 and 'PASS ALU' in log,width
 results[str(width)]=dict(passed=True,vectors=len(vectors),log=log,
  source_sha256={s.relative_to(ROOT).as_posix():hashlib.sha256(s.read_bytes()).hexdigest() for s in sources+[path]})
(OUT/'alu.json').write_text(json.dumps(dict(passed=True,tests=results),indent=2)+'\n')
