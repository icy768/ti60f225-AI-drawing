"""Full VGA accelerator job with cached IN, actual refresh, asynchronous control.

Reuses the independently checked official golden VGA vectors, validating hashes.
Periodic stream stalls exercise flow control; they are not a DDR timing model.
"""
from pathlib import Path
import hashlib,json,re,subprocess,sys,zipfile
ROOT=Path(__file__).resolve().parent
BASE=ROOT/'validation/vga_performance/optimized'
OUT=ROOT/'validation/latency_vga';OUT.mkdir(exist_ok=True)
BIN=ROOT.parent/'tools/iverilog/mingw64/bin'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
# Keep the exact checked VGA fixture available in a fresh checkout; generated
# simulation binaries and large working folders remain ignored.
with zipfile.ZipFile(ROOT/'sim/fixtures/vga_reference.zip') as archive:
    fixture_hashes=json.loads(archive.read('sha256.json'))
    BASE.mkdir(parents=True,exist_ok=True)
    for name,expected_hash in fixture_hashes.items():
        assert name in ['input.hex','expected.hex','records.hex','result.json']
        data=archive.read(name)
        assert hashlib.sha256(data).hexdigest()==expected_hash,name
        target=BASE/name
        if not target.exists():target.write_bytes(data)
        assert sha(target)==expected_hash,'Local reference fixture changed: '+name
old=json.loads((BASE/'result.json').read_text())
assert old['passed'] and old['weights_sha256']==sha(ROOT/'model/net_blob.bin')
for f,h in old['source_sha256'].items():assert sha(ROOT/f'rtl/{f}.v')==h,f
# The top-level statistics selector can change; the complete current RTL output
# is checked against the unchanged golden image below, not against old HDL text.
expected=bytes(v for word in (BASE/'expected.hex').read_text().split() for v in int(word,16).to_bytes(3,'little'))
assert hashlib.sha256(expected).hexdigest()==old['expected_image_sha256']
if '--check-vectors' in sys.argv:
    print('PASS: independent VGA fixture hashes, original weights and decoded golden image')
    sys.exit(0)
records=(BASE/'records.hex').read_text().split();nrec=len(records)//3
tb=r'''
`timescale 1ns/1ps
module tb;
 reg clk=0,nc=0;always #5 clk=~clk;always #3.333 nc=~nc;
 reg rst=1,cw=0,csel=0,start=0;reg[4:0] layer=0,lane=0;reg[11:0] addr=0;reg[37:0] data=0;
 reg[23:0] pixels[0:307199],expected[0:307199];reg[31:0] records[0:NWORDS-1];
 reg replay_busy=0;integer ni=0,no=0,cycle=0,i;
 wire iv=replay_busy&&(cycle%257>=16),sr=cycle%31>=5;
 wire ready,valid,rstart,idle,done,ok,reject;wire[23:0] out;
 wire[31:0] job_cycles,pass_cycles,ins,outs;
 real started;
 sc_engine_cdc dut(.clk(clk),.system_reset(rst),.nc(nc),.nrst(rst),
 .sink_ready(sr),.sink_data(out),.sink_valid(valid),.new_frame(),
 .replay_data(pixels[ni<307200?ni:0]),.replay_valid(iv),.replay_ready(ready),.replay_start(rstart),.replay_busy(replay_busy),
 .video_start(start),.video_style(2'd0),.video_mode(1'b1),.video_bank(2'd2),.upload_bank(),
 .video_idle(idle),.video_done(done),.video_ok(ok),.video_styles_ready(),
 .cpu_cfg_we(cw),.cpu_cfg_sel(csel),.cpu_cfg_lane(lane),.cpu_cfg_layer(layer),.cpu_cfg_addr(addr),.cpu_cfg_data(data),.cpu_cfg_rejects(reject),
 .run_cycles(pass_cycles),.first_output_cycles(),.input_stalls(ins),.output_stalls(outs),
 .auto_cycles(job_cycles),.auto_frames(),.auto_writes(),.auto_errors(),.errors());
 always @(posedge nc)if(!rst)begin
  cycle<=cycle+1;
  if(rstart)begin replay_busy<=1;ni<=0;no<=0;end
  if(iv&&ready)begin ni<=ni+1;if(ni==307199)replay_busy<=0;end
  if(valid&&sr)begin
   if(out!==expected[no])$fatal(1,"VGA mismatch pixel %0d got %h expected %h",no,out,expected[no]);
   no<=no+1;
   if(no%65536==65535)begin $display("VGA checked %0d",no+1);$fflush();end
  end
 end
 initial begin
  $readmemh("validation/vga_performance/optimized/input.hex",pixels);
  $readmemh("validation/vga_performance/optimized/expected.hex",expected);
  $readmemh("validation/vga_performance/optimized/records.hex",records);
  repeat(10)@(negedge clk);rst=0;repeat(1200)@(negedge clk);
  for(i=0;i<NREC;i=i+1)begin
   wait(idle);@(negedge clk);csel=records[3*i][31];lane=records[3*i][25:21];layer=records[3*i][20:16];addr=records[3*i][11:0];
   data={records[3*i+2][5:0],records[3*i+1]};cw=1;@(negedge clk);cw=0;repeat(2)@(negedge clk);
  end
  wait(idle);repeat(20)@(negedge clk);if(reject)$fatal(1,"Config rejected");
  $display("VGA real engine start with refreshed IN and stream backpressure");$fflush();
  started=$realtime;start=1;@(negedge clk);start=0;wait(done);@(negedge clk);
  if(!ok||no!=307200||ni!=307200||dut.fast.auto_writes!=16||dut.fast.auto_errors||dut.fast.errors)$fatal(1,"VGA completion");
  $display("PASS VGA CDC pixels=307200 job_cycles=%0d pass_cycles=%0d input_stalls=%0d output_stalls=%0d elapsed_ns=%0.3f",job_cycles,pass_cycles,ins,outs,$realtime-started);$finish;
 end
 initial begin #100000000;$fatal(1,"VGA timeout");end
endmodule
'''.replace('NWORDS',str(len(records))).replace('NREC',str(nrec))
(OUT/'tb.v').write_text(tb,encoding='ascii')
rtl=['sc_engine_cdc','sc_engine','sc_in_refresh','sc_in_math','sc_in_alu','stylenet_top','common','conv_layer','mac','requant','swg3','swg3b']
exe=OUT/'test.vvp'
subprocess.run([str(BIN/'iverilog.exe'),'-g2012','-s','tb','-o',str(exe),str(OUT/'tb.v'),*[f'rtl/{f}.v' for f in rtl]],cwd=ROOT,check=True)
with (OUT/'simulation.log').open('w') as log: run=subprocess.run([str(BIN/'vvp.exe'),str(exe)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
log=(OUT/'simulation.log').read_text();print(log,flush=True)
assert run.returncode==0 and 'PASS VGA CDC' in log
values={k:float(v) if '.' in v else int(v) for k,v in re.findall(r'(\w+)=(\d+(?:\.\d+)?)',log)}
(OUT/'result.json').write_text(json.dumps(dict(passed=True,hardware_verified=False,pixels_exact=307200,
    includes_dynamic_in=True,includes_ddr_hdmi=False,stream_backpressure=True,core_mhz=100,engine_mhz=150,
    measurements=values,simulated_job_ms=values['elapsed_ns']/1e6,
    source_sha256={f'rtl/{f}.v':sha(ROOT/f'rtl/{f}.v') for f in rtl},
    vector_sha256={p.name:sha(p) for p in BASE.glob('*.hex')}),indent=2),encoding='utf-8')
