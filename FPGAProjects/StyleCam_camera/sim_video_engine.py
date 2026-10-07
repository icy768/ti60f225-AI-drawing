"""Nine V21 real-network frames: all styles, first IN, two rotating refreshes."""
from pathlib import Path
import hashlib, json, re, subprocess, sys
import numpy as np
from reference import ROOT, run, pack_coef, load, coef
from compact_in_constants import compact
from export_in_constants import export
S=ROOT/'validation/video_engine';S.mkdir(exist_ok=True)
BIN=Path(__import__('os').environ.get('ICARUS_BIN',ROOT.parent/'tools/iverilog/mingw64/bin'))
sys.path.insert(0,str(ROOT.parent/'StyleCam/algo'))
import golden, torch
torch.set_num_threads(2)
official=golden.load(str(ROOT/'model/qparams'))
export(32,24,S/'constants.mem');compact(S/'constants.mem')
images=[np.random.default_rng(17).integers(0,256,(24,32,3),dtype=np.uint8),np.random.default_rng(99).integers(0,96,(24,32,3),dtype=np.uint8)]
expected=[None]*9;words=[];q=load();reference_source=(ROOT/'reference.py').read_text().replace('M,B=coef(L,st,style);','M,B=override_coefficients[i];')
for style in range(3):
    first,stats,coefficients=run(images[0],style)
    independent,independent_stats,dumps=golden.run(official,images[0],style,dump=True)
    assert np.array_equal(first,independent),('official pixel reference',style)
    for a,b in zip(stats,independent_stats):
        if b is not None: assert a[2]==b[2] and np.array_equal(a[0],b[0]) and np.array_equal(a[1],b[1])
    for (m,b),d in zip(coefficients,dumps): assert np.array_equal(m,d['M']) and np.array_equal(b,d['B'])
    oracle=dict(__file__=str(ROOT/'reference.py'),__name__='oracle',override_coefficients=coefficients)
    exec(compile(reference_source,str(ROOT/'reference.py'),'exec'),oracle)
    second,newstats,_=oracle['run'](images[1],style)
    other,_,_=golden.run(official,images[1],style,prev_stats=independent_stats)
    assert np.array_equal(second,other),('previous-frame IN reference',style)
    refresh0=coef(q['layers'][0],newstats[0],style)
    oracle['override_coefficients']=list(coefficients);oracle['override_coefficients'][0]=refresh0
    third,nextstats,_=oracle['run'](images[1],style)
    refresh1=coef(q['layers'][1],nextstats[1],style)
    expected[style]=first;expected[3+style]=second;expected[6+style]=third
    for layer,(ms,bs) in list(enumerate(coefficients[:12]))+[(0,refresh0),(1,refresh1)]:
        words.extend(int.from_bytes(pack_coef(layer,0,m,b)[3:],'little') for m,b in zip(ms,bs))
assert len(words)==936
for name,values,digits in [
 ('images',[int(r)|(int(g)<<8)|(int(b)<<16) for im in images for r,g,b in im.reshape(-1,3)],6),
 ('expected',[int(r)|(int(g)<<8)|(int(b)<<16) for im in expected for r,g,b in im.reshape(-1,3)],6),
 ('coefficients',words,10)]:
    (S/(name+'.hex')).write_text('\n'.join(f'{x:0{digits}x}' for x in values)+'\n',encoding='ascii')
net=re.sub(r'\.(W|H|WL|HL)\((\d+)\)',lambda m:f'.{m[1]}({int(m[2])//20})',(ROOT/'rtl/stylenet_top.v').read_text())
(S/'net.v').write_text(net,encoding='utf-8')
tb=r'''
module tb;
 reg clk=0;always #5 clk=~clk;
 reg reset=0,start_video=0,mode=0;reg [1:0] style=0;
 wire idle,done,ok;wire [2:0] styles_ready;wire [23:0] sink;wire sv,ready,replay_start;
 reg source_busy=0;integer epoch=0,index=0,outindex=0,cycle=0,checked=0,ci,l,c,st;
 reg [23:0] images[0:1535],expected[0:6911];reg [37:0] coefficients[0:935];
 wire iv=source_busy&&(cycle%7!=0),sink_ready=cycle%11!=0;
 wire [10:0] input_base=epoch<3?0:768;
 sc_engine #(.WIDTH(32),.HEIGHT(24),.IN_TRACE(1),.IN_FILE("validation/video_engine/constants.mem")) dut(
 .clk(clk),.system_reset(reset),
 .sink_ready(sink_ready),.sink_data(sink),.sink_valid(sv),.new_frame(),
 .replay_data(images[input_base+index]),.replay_valid(iv),.replay_ready(ready),.replay_start(replay_start),.replay_busy(source_busy),
 .video_start(start_video),.video_style(style),.video_mode(mode),.video_idle(idle),.video_done(done),.video_ok(ok),.video_styles_ready(styles_ready),
 .cpu_cfg_we(1'b0),.cpu_cfg_layer(5'd0),.cpu_cfg_addr(12'd0),.cpu_cfg_data(38'd0),.cpu_cfg_rejects(),
 .run_cycles(),.first_output_cycles(),.input_stalls(),.output_stalls(),.auto_cycles(),.auto_frames(),.auto_writes(),.auto_errors(),.errors());
 always @(posedge clk)begin
  cycle<=cycle+1;
  if(replay_start)begin index<=0;outindex<=0;source_busy<=1;end
  if(iv&&ready)begin index<=index+1;if(index==767)source_busy<=0;end
  if(sv&&sink_ready)begin
   if(dut.auto_layer==12||dut.auto_mode)begin
    if(sink!==expected[epoch*768+outindex])$fatal(1,"V21 pixel epoch %0d style %0d index %0d got %h expected %h",epoch,style,outindex,sink,expected[epoch*768+outindex]);
    checked<=checked+1;
   end
   outindex<=outindex+1;
  end
  if(dut.in_cfg_we&&dut.active)$fatal(1,"IN wrote during a frame");
  if(dut.cfg_we)$fatal(1,"Unexpected host IN write");
 end
 task job;begin
  wait(idle);@(negedge clk);start_video=1;@(negedge clk);start_video=0;wait(done);@(negedge clk);
  if(!ok||dut.auto_errors||dut.errors||!styles_ready[style])$fatal(1,"V21 autonomous IN failed style %0d",style);
 end endtask
 initial begin
  $readmemh("validation/video_engine/images.hex",images);$readmemh("validation/video_engine/expected.hex",expected);$readmemh("validation/video_engine/coefficients.hex",coefficients);
  repeat(1200)@(negedge clk);
  for(st=0;st<3;st=st+1)begin
   style=st;epoch=st;mode=0;job;
   if(dut.auto_frames!=13||dut.auto_writes!=272)$fatal(1,"Initial calibration counts");
   ci=st*312;for(l=0;l<12;l=l+1)for(c=0;c<((l==0||l==11)?16:24);c=c+1)begin
    if(dut.in_update.trace[st*288+l*24+c]!==coefficients[ci])$fatal(1,"V21 initial coefficient style %0d layer %0d channel %0d",st,l,c);ci=ci+1;
   end
   $display("PASS V21 style %0d initial IN: 272 coefficients and 768 pixels exact",st);
  end
  if(styles_ready!=7)$fatal(1,"Style readiness after no-reset switching");
  for(st=0;st<3;st=st+1)begin
   style=st;epoch=3+st;mode=1;job;
   if(dut.auto_frames!=1||dut.auto_writes!=16||dut.rotation[st]!=1)$fatal(1,"Layer0 rotating counts");
   for(c=0;c<16;c=c+1)if(dut.in_update.trace[st*288+c]!==coefficients[st*312+272+c])$fatal(1,"V21 next-frame layer0 coefficient");
   $display("PASS V21 style %0d changed frame: 768 pixels and 16 refreshed coefficients exact",st);
  end
  for(st=0;st<3;st=st+1)begin
   style=st;epoch=6+st;mode=1;job;
   if(dut.auto_frames!=1||dut.auto_writes!=24||dut.rotation[st]!=2)$fatal(1,"Layer1 rotating counts");
   for(c=0;c<24;c=c+1)if(dut.in_update.trace[st*288+24+c]!==coefficients[st*312+288+c])$fatal(1,"V21 next-frame layer1 coefficient");
   $display("PASS V21 style %0d refreshed layer0 used: 768 pixels and 24 layer1 coefficients exact",st);
  end
  if(checked!=6912)$fatal(1,"V21 pixels %0d",checked);
  reset=1;repeat(5)@(negedge clk);if(styles_ready||done)$fatal(1,"V21 autonomous reset");
  $display("PASS V21 all styles: 6912 pixels, 936 IN coefficients, no-reset style switching, backpressure and reset");$finish;
 end
 initial begin #120000000;$fatal(1,"V21 video engine timeout");end
endmodule
'''
(S/'tb.v').write_text(tb,encoding='ascii')
files=['sc_engine','sc_in_refresh','sc_in_math','sc_in_alu','common','conv_layer','mac','requant','swg3','swg3b']
exe=S/'engine.vvp'
subprocess.run([str(BIN/'iverilog.exe'),'-g2012','-s','tb','-o',str(exe),str(S/'tb.v'),str(S/'net.v'),*[str(ROOT/f'rtl/{n}.v') for n in files]],cwd=ROOT,check=True)
print('Running V21 13-layer network, all three styles and dynamic IN',flush=True)
with (S/'simulation.log').open('w',encoding='utf-8') as f:r=subprocess.run([str(BIN/'vvp.exe'),str(exe)],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
log=(S/'simulation.log').read_text(encoding='utf-8',errors='replace');print(log,flush=True)
assert r.returncode==0 and 'PASS V21 all styles' in log,log
(S/'result.json').write_text(json.dumps(dict(passed=True,network='v21b_ukiyoe_qat900_640x480',real_network=True,styles=[0,1,2],
 initial_coefficients_exact=816,changed_frame_coefficients_exact=120,pixels_exact=6912,frames=9,
 no_reset_style_switching=True,independent_official_golden_reference=True,host_IN_writes=0,input_backpressure=True,output_backpressure=True,
 network_blob_sha256=hashlib.sha256((ROOT/'model/net_blob.bin').read_bytes()).hexdigest()),indent=2),encoding='utf-8')
