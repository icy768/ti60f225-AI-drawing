"""Independent integer ALU checks and asynchronous three-bank upload pressure."""
from pathlib import Path
import hashlib, json, math, os, random, subprocess

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'validation/optimization'
OUT.mkdir(parents=True, exist_ok=True)
BIN = Path(os.environ.get('ICARUS_BIN', ROOT.parent / 'tools/iverilog/mingw64/bin'))

def simulate(name, bench, files):
    tb = OUT / (name + '.v')
    tb.write_text(bench, encoding='utf-8')
    exe = OUT / (name + '.vvp')
    subprocess.run([str(BIN/'iverilog.exe'), '-g2012', '-s', 'tb', '-o', str(exe), str(tb),
                    *[str(ROOT/'rtl'/f) for f in files]], cwd=ROOT, check=True)
    p = subprocess.run([str(BIN/'vvp.exe'), str(exe)], cwd=ROOT, capture_output=True, text=True, timeout=180)
    (OUT/(name+'.log')).write_text(p.stdout+p.stderr, encoding='utf-8')
    print(p.stdout, flush=True)
    assert p.returncode == 0 and 'PASS' in p.stdout, p.stderr
    return p.stdout

rng = random.Random(20261013)
mask = (1 << 160) - 1
vectors = []
for op in range(6):
    cases = [(a,b) for a in [0,1,2,3,mask,1<<159,(1<<159)-1]
             for b in ([0,1,2,31,32,40,159,160,161,255] if op==5 else [0,1,2,3,1<<159,mask])]
    cases += [(rng.getrandbits(160),rng.randrange(256) if op==5 else rng.getrandbits(160)) for _ in range(160)]
    # Exact halfway quotients of both parities, across limb boundaries.
    if op == 1:
        cases += [(q*(1<<k)+(1<<(k-1)),1<<k) for k in [1,31,32,40,80] for q in [2,3,100,101]]
    for a,b in cases:
        error = int(op==1 and b==0)
        borrow = int(op==4 and a<b)
        if op == 0: expected = a*b & mask
        elif op in (1,5):
            divisor = b if op==1 else 1<<b
            if divisor:
                q,r = divmod(a,divisor)
                expected = (q+int(2*r>divisor or (2*r==divisor and q&1))) & mask
            else: expected = 0
        elif op==2: expected = math.isqrt(a)
        elif op==3: expected = (a+b)&mask
        else: expected = (a-b)&mask
        vectors.append(f'{op:x}{a:040x}{b:040x}{expected:040x}{error:x}{borrow:x}')
(OUT/'alu.hex').write_text('\n'.join(vectors)+'\n', encoding='ascii')
alu = r'''
module tb;
 reg clk=0;always #5 clk=~clk;reg rst=1,start=0;reg[2:0] op;reg[159:0] a,b;
 wire busy,done,error,borrow;wire[159:0] result;
 reg[491:0] vectors[0:COUNT-1];reg[159:0] expected;reg[3:0] e,bo,code;integer i,c;
 sc_in_alu dut(clk,rst,start,op,a,b,busy,done,error,result,borrow);
 initial begin
  $readmemh("validation/optimization/alu.hex",vectors);repeat(3)@(negedge clk);rst=0;
  for(i=0;i<COUNT;i=i+1)begin
   {code,a,b,expected,e,bo}=vectors[i];op=code;start=1;@(negedge clk);start=0;c=0;
   while(!done)begin @(negedge clk);c=c+1;if(c>3000)$fatal(1,"ALU timeout %d",i);end
   if(error!==e[0]||borrow!==bo[0]||result!==expected)$fatal(1,"ALU vector=%0d op=%0d actual=%h want=%h borrow=%b want=%b",i,op,result,expected,borrow,bo);
   @(negedge clk);
  end
  a=160'hffffffffffffffffffffffffffffffffffffffff;b=3;op=1;start=1;@(negedge clk);start=0;
  repeat(40)@(negedge clk);rst=1;@(negedge clk);if(busy||done)$fatal(1,"reset in division");
  $display("PASS ALU COUNT independent Python integer vectors, full 160-bit range, RNE ties, carry/borrow, reset");$finish;
 end
endmodule
'''.replace('COUNT',str(len(vectors)))
simulate('alu', alu, ['sc_in_alu.v'])

upload = r'''
`timescale 1ns/1ps
module tb;
 reg uc=0,ac=0,pc=0;always #3 uc=~uc;always #5 ac=~ac;always #7 pc=~pc;
 reg rst=1,nf=0,pv=0;reg[23:0] pixel;reg[1:0] bank=0;wire ready,complete;
 wire[31:0] awaddr;wire av,wv,br;wire[127:0] wd;reg bv=0;
 integer cycle=0,phase=0,delay_b=0,words=0,frame=0,checked=0,stalls=0;
 reg[31:0] address;reg[1:0] response=0;
 wire ar=phase==0&&cycle%5==0,wr=phase==1&&cycle%7==0;
 function[31:0] base(input integer f);begin base=f==0?32'h400000:f==1?32'h600000:32'ha00000;end endfunction
 function[23:0] px(input integer f,input integer i);begin px=(f*24'h3579ab)^(i*24'h010307);end endfunction
 sc_display #(.IW(64),.IH(8),.FONT(""),.TEXT("")) dut(
 .uc(uc),.urst(rst),.ac(ac),.arst(rst),.pc(pc),.prst(rst),.calibrated(1'b1),
 .pixel(pixel),.pv(pv),.pready(ready),.new_frame(nf),.original_frame(1'b0),.mode(2'd1),.status(),
 .write_bank(bank),.publish(1'b0),.publish_bank(2'd0),.publish_orig(2'd0),.output_complete(complete),.shown_valid(),.shown_bank(),
 .osd_we(1'b0),.osd_addr(11'd0),.osd_data(8'd0),
 .awaddr(awaddr),.awvalid(av),.awready(ar),.wdata(wd),.wvalid(wv),.wready(wr),.bvalid(bv),.bresp(response),.bready(br),
 .araddr(),.arvalid(),.arready(1'b0),.rdata(128'd0),.rvalid(1'b0),.rlast(1'b0),.rresp(2'd0),.rready(),.hs(),.vs(),.de(),.red(),.green(),.blue());
 integer k;
 always @(posedge ac)if(!rst)begin
  cycle<=cycle+1;
  if(av&&ar)begin
   if(awaddr!==base(frame)+words*16)$fatal(1,"upload address f=%d word=%d %h",frame,words,awaddr);
   address<=awaddr;phase<=1;
  end
  if(wv&&wr)begin
   for(k=0;k<4;k=k+1)if(wd[k*32+:32]!=={8'd0,px(frame,words*4+k)})$fatal(1,"upload pixel f=%d w=%d lane=%d",frame,words,k);
   checked<=checked+4;phase<=2;delay_b<=cycle%11+4;response<=(frame==1&&words==127)?2'd2:2'd0;
  end
  if(phase==2&&!bv)begin if(delay_b==0)bv<=1;else delay_b<=delay_b-1;end
  if(bv&&br)begin bv<=0;phase<=0;words<=words+1;end
  if(words>0&&words<128&&complete)$fatal(1,"published before final B response");
 end
 always @(posedge uc)if(!rst&&pv&&!ready)stalls<=stalls+1;
 integer i;
 initial begin
  repeat(10)@(negedge uc);rst=0;repeat(5)@(negedge uc);
  for(frame=0;frame<3;frame=frame+1)begin
   bank=frame;words=0;nf=1;@(negedge uc);nf=0;
   for(i=0;i<512;i=i+1)begin
    pixel=px(frame,i);pv=1;
    @(posedge uc);while(!ready)@(posedge uc);
    @(negedge uc);
   end
   pv=0;wait(words==128);repeat(12)@(negedge uc);
   if(frame==1)begin if(complete||dut.valid_banks[1])$fatal(1,"error frame committed");end
   else if(!complete||!dut.valid_banks[frame])$fatal(1,"good frame incomplete %d",frame);
  end
  if(checked!=1536||stalls==0||dut.write_errors!=1)$fatal(1,"upload coverage");
  rst=1;repeat(10)@(negedge uc);if(complete||dut.valid_banks)$fatal(1,"upload reset");
  $display("PASS three-bank upload: 1536 exact pixels, asynchronous clocks, FIFO-full backpressure, delayed AW/W/B, final-B error, reset");$finish;
 end
 initial begin #2000000;$fatal(1,"upload timeout");end
endmodule
'''
simulate('upload', upload, ['sc_display.v','sc_async_fifo.v','common.v'])
files=['sc_in_alu.v','sc_in_math.v','sc_display.v','sc_async_fifo.v']
(OUT/'result.json').write_text(json.dumps(dict(passed=True,alu_vectors=len(vectors),upload_pixels=1536,
    three_output_banks=True,asynchronous_upload=True,full_fifo_backpressure=True,final_b_error=True,
    source_sha256={f:hashlib.sha256((ROOT/'rtl'/f).read_bytes()).hexdigest() for f in files}),indent=2)+'\n',encoding='utf-8')
