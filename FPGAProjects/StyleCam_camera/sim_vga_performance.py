"""Pixel-exact full VGA pass, comparing PE6/PE12 with identical weights and IN.

This measures network cycles with unstalled input/output, not board or HDMI FPS.
Run with --variant baseline or optimized; each run uses its own evidence folder.
"""
from pathlib import Path
import argparse, hashlib, json, os, re, subprocess, sys
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent
ap = argparse.ArgumentParser()
ap.add_argument('--variant', choices=['baseline','optimized'], default='optimized')
args = ap.parse_args()
OUT = ROOT/'validation/vga_performance'/args.variant
OUT.mkdir(parents=True, exist_ok=True)
BIN = Path(os.environ.get('ICARUS_BIN', ROOT.parent/'tools/iverilog/mingw64/bin'))
sys.path.insert(0,str(ROOT.parent/'StyleCam/algo'))
import golden, torch
torch.set_num_threads(2)
im = np.array(Image.open(ROOT.parent/'StyleCam/data/val2017/000000000139.jpg').convert('RGB').resize((640,480)))
q = golden.load(str(ROOT/'model/qparams'))
expected,_,dumps = golden.run(q,im,0,dump=True)
records = np.frombuffer((ROOT/'model/net_blob.bin').read_bytes(),dtype='<u4')[4:].reshape(-1,3).tolist()
for layer,d in enumerate(dumps):
    for c,(m,b) in enumerate(zip(d['M'],d['B'])):
        word=((int(m)&0x3ffff)<<20)|(int(b)&0xfffff)
        records.append([(layer<<16)|c,word&0xffffffff,word>>32])
for name,values,width in [
    ('input',[int(r)|(int(g)<<8)|(int(b)<<16) for r,g,b in im.reshape(-1,3)],6),
    ('expected',[int(r)|(int(g)<<8)|(int(b)<<16) for r,g,b in expected.reshape(-1,3)],6),
    ('records',[v for r in records for v in r],8)]:
    (OUT/(name+'.hex')).write_text('\n'.join(f'{x:0{width}x}' for x in values)+'\n',encoding='ascii')
net=(ROOT/'rtl/stylenet_top.v').read_text(encoding='utf-8')
pe = 6 if args.variant == 'baseline' else 12
net, replacements = re.subn(r'\.PE\((?:6|12)\), \.CFG_PE\(6\)',
                            f'.PE({pe}), .CFG_PE(6)', net)
assert replacements == 1, 'Expected exactly one configurable output layer'
(OUT/'net.v').write_text(net,encoding='utf-8')
tb=r'''
`timescale 1ns/1ps
module tb;
 reg clk=0;always #5 clk=~clk;reg rst=1,active=0,cw=0,csel=0;
 reg[4:0] layer=0,lane=0;reg[11:0] addr=0;reg[37:0] data=0;
 reg[23:0] pixels[0:307199],expected[0:307199];reg[31:0] records[0:NWORDS-1];
 integer ni=0,no=0,cycles=0,first=0,i;
 wire iv=active&&ni<307200;wire ready,valid;wire[23:0] output_pixel;
 stylenet_top dut(.clk(clk),.rst(rst),.style(4'd0),.cfg_we(cw),.cfg_sel(csel),.cfg_layer(layer),.cfg_lane(lane),.cfg_addr(addr),.cfg_data(data),
 .i_data(pixels[ni<307200?ni:0]),.i_valid(iv),.i_ready(ready),.o_data(output_pixel),.o_valid(valid),.o_ready(1'b1),
 .st_sel(5'd31),.st_arm(1'b0),.st_fs(1'b0),.st_fe(1'b0),.st_idx(8'd0),.st_s1(),.st_s2(),.st_done(),.st_busy());
 always @(posedge clk)if(active)begin
  cycles<=cycles+1;
  if(iv&&ready)ni<=ni+1;
  if(valid)begin
   if(output_pixel!==expected[no])$fatal(1,"VGA pixel %d actual=%h expected=%h",no,output_pixel,expected[no]);
   if(no==0)first<=cycles;
   no<=no+1;
   if(no%32768==32767)begin $display("VGA checked %0d pixels, cycles=%0d",no+1,cycles);$fflush();end
   if(no==307199)begin
    if(ni!=307200)$fatal(1,"input count");
    $display("PASS VGA VARIANT pixels=307200 cycles=%0d first=%0d",cycles,first);$finish;
   end
  end
 end
 initial begin
  $readmemh("FOLDER/input.hex",pixels);$readmemh("FOLDER/expected.hex",expected);$readmemh("FOLDER/records.hex",records);
  repeat(10)@(negedge clk);rst=0;
  for(i=0;i<NREC;i=i+1)begin
   csel=records[3*i][31];lane=records[3*i][25:21];layer=records[3*i][20:16];addr=records[3*i][11:0];
   data={records[3*i+2][5:0],records[3*i+1]};cw=1;@(negedge clk);cw=0;repeat(2)@(negedge clk);
  end
  repeat(10)@(negedge clk);rst=1;repeat(5)@(negedge clk);rst=0;active=1;
  $display("VGA VARIANT start: 640x480, original blob and official golden IN coefficients");$fflush();
 end
 initial begin #120000000;$fatal(1,"VGA timeout");end
endmodule
'''.replace('NWORDS',str(3*len(records))).replace('NREC',str(len(records))).replace('VARIANT',args.variant).replace('FOLDER',OUT.relative_to(ROOT).as_posix())
(OUT/'tb.v').write_text(tb,encoding='ascii')
exe=OUT/'test.vvp'
rtl=['common','conv_layer','mac','requant','swg3','swg3b']
subprocess.run([str(BIN/'iverilog.exe'),'-g2012','-s','tb','-o',str(exe),str(OUT/'tb.v'),str(OUT/'net.v'),
                *[str(ROOT/'rtl'/(f+'.v')) for f in rtl]],cwd=ROOT,check=True)
print('Simulating full VGA',args.variant,flush=True)
with (OUT/'simulation.log').open('w',encoding='utf-8') as f:
    result=subprocess.run([str(BIN/'vvp.exe'),str(exe)],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,timeout=3600)
log=(OUT/'simulation.log').read_text(encoding='utf-8');print(log,flush=True)
match=re.search(r'PASS VGA \w+ pixels=307200 cycles=(\d+) first=(\d+)',log)
assert result.returncode==0 and match,log
cycles,first=map(int,match.groups())
report=dict(passed=True,variant=args.variant,pixels_exact=307200,cycles=cycles,first_output_cycles=first,
    simulated_pass_ms_100mhz=cycles/100000,max_passes_per_second_100mhz=100000000/cycles,
    includes_ddr_hdmi_or_dynamic_in=False,weights_sha256=hashlib.sha256((ROOT/'model/net_blob.bin').read_bytes()).hexdigest(),
    expected_image_sha256=hashlib.sha256(expected.tobytes()).hexdigest(),
    source_sha256={f:hashlib.sha256((ROOT/'rtl'/(f+'.v')).read_bytes()).hexdigest() for f in rtl})
(OUT/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
