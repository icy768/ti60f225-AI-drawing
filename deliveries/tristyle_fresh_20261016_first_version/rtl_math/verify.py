"""Sample actual frozen constants; independent Fraction oracle; Icarus functional test."""
import ctypes,datetime,hashlib,json,os,pathlib,random,subprocess,sys
if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8',errors='replace')
from fractions import Fraction
ROOT=pathlib.Path(__file__).resolve().parents[1];HERE=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'claude_impl'))
from int_ref import IntGraph
pack=ROOT/'deployment_refine6000/tristyle_v3_hw.bin';g=IntGraph(pack)
build=HERE/'build';build.mkdir(exist_ok=True);rng=random.Random(1660)
def rne(x,sh):return round(Fraction(x,1<<sh)) if sh>=0 else x<<(-sh)
def sat(x):return max(0,min(255,x))
def bits(x,n):return int(x)&((1<<n)-1)
xs=[];ws=[];params=[];case_map=[]
for name,d in g.c.items():
 for oc in (0,int(d['W'].shape[0])-1):
  w=d['W'][oc].reshape(-1).tolist();N=len(w)
  for kind in ('zero','zeropoint','white','random'):
   x=([0]*N if kind=='zero' else [d['in_zp']]*N if kind=='zeropoint' else [255]*N if kind=='white' else [rng.randrange(256) for _ in w])
   bias=int(d['B'][oc]);m=int(d['M'][0,oc,0,0]);e=int(d['E'][oc]);off=len(xs)
   acc=bias+sum((a-d['in_zp'])*b for a,b in zip(x,w));assert -(1<<31)<=acc<(1<<31)
   y=sat(rne(acc*m,31-e)+d['out_zp']);y=max(y,d['out_zp']) if d['relu'] else y
   fields=[(bias,0,32),(m,32,32),(e,64,8),(d['in_zp'],72,8),(d['out_zp'],80,8),(int(d['relu']),88,1),(acc,89,32),(y,121,8),(off,129,32),(N,161,16)]
   params.append(sum(bits(a,n)<<shift for a,shift,n in fields));xs+=x;ws+=w
   case_map.append({'conv':name,'oc':oc,'kind':kind,'fan_in':N})
(build/'params.mem').write_text('\n'.join(f'{p:064x}' for p in params))
(build/'xs.mem').write_text('\n'.join(f'{p:02x}' for p in xs))
(build/'ws.mem').write_text('\n'.join(f'{bits(p,8):02x}' for p in ws))
merge=[];merge_map=[]
nodes=g.meta['graph']['shared']+sum(g.meta['graph']['experts'],[])
for n in nodes:
 if n['op'] not in ('add','cat'):continue
 rs=n['integer']['inputs'];assert n['integer']['guard_bits']==16
 # For cat, each input independently passes through the scalar rescaler.
 for ri in (range(1) if n['op']=='add' else range(len(rs))):
  ra=rs[0] if n['op']=='add' else rs[ri];rb=rs[1] if n['op']=='add' else ra;use=n['op']=='add'
  for a,b in [(0,0),(255,255),(0,255),(255,0),(ra['in_zp'],rb['in_zp'])]+[(rng.randrange(256),rng.randrange(256)) for _ in range(5)]:
   aa=rne((a-ra['in_zp'])*ra['multiplier'],31-ra['exponent']);bb=rne((b-rb['in_zp'])*rb['multiplier'],31-rb['exponent']) if use else 0
   y=sat(rne(aa+bb,16)+n['integer']['out_zp'])
   fields=[(a,0,8),(b,8,8),(ra['in_zp'],16,8),(rb['in_zp'],24,8),(n['integer']['out_zp'],32,8),(ra['multiplier'],40,32),(rb['multiplier'],72,32),(ra['exponent'],104,8),(rb['exponent'],112,8),(int(use),120,1),(y,121,8)]
   merge.append(sum(bits(a,n)<<s for a,s,n in fields));merge_map.append({'op':n['op'],'id':n['id'],'input':ri})
(build/'merge.mem').write_text('\n'.join(f'{p:064x}' for p in merge))
rounds=[(x,sh,rne(x,sh)) for sh in (0,1,2,3,16,31,40,63,-2) for x in (0,1,-1,3,-3,5,-5,7,-7,12,-12,20,-20,28,-28,2147483647,-2147483648)]
rounds += [(1<<62,63,0),(-(1<<63),64,0),((1<<63)-1,64,0)]
(build/'round.mem').write_text('\n'.join(f'{bits(x,64)|(bits(sh,9)<<64)|(bits(y,64)<<73):048x}' for x,sh,y in rounds))
tb='''`timescale 1ns/1ps
module testbench;
 reg clk=0;always #5 clk=~clk;
 reg rst=1,clear=0,valid=0;reg[7:0]x=0,zin=0;reg signed[7:0]w=0;
 reg signed[31:0]bias=0,mult=0;reg signed[7:0]expn=0;reg[7:0]zout=0;reg relu=0;
 wire signed[31:0]acc;wire overflow;wire[7:0]y;
 mac_dot8 mac(clk,rst,clear,valid,x,zin,w,bias,acc,overflow);
 requant32 rq(acc,mult,expn,zout,relu,y);
 reg[255:0]p[0:NCASES-1];reg[7:0]xs[0:NSAMPLES-1],ws[0:NSAMPLES-1];reg[255:0]mp[0:NMERGE-1];
 reg[7:0]a=0,b=0,za=0,zb=0,zo=0;reg signed[31:0]ma=0,mb=0;reg signed[7:0]ea=0,eb=0;reg use_b=0;wire[7:0]my;
 merge_requant8 mq(a,b,za,zb,zo,ma,mb,ea,eb,use_b,my);
 reg[191:0]rp[0:NROUND-1];reg signed[63:0]rx=0;reg signed[8:0]rsh=0;wire signed[63:0]ry;
 rne_shift64 rounder(rx,rsh,ry);
 integer i,j,off,n;
 initial begin
  $readmemh("params.mem",p);$readmemh("xs.mem",xs);$readmemh("ws.mem",ws);$readmemh("merge.mem",mp);$readmemh("round.mem",rp);
  repeat(2) @(negedge clk);rst=0;
  for(i=0;i<NCASES;i=i+1)begin
   @(negedge clk);clear=1;valid=0;bias=p[i][31:0];mult=p[i][63:32];expn=p[i][71:64];zin=p[i][79:72];zout=p[i][87:80];relu=p[i][88];off=p[i][160:129];n=p[i][176:161];
   @(negedge clk);clear=0;valid=1;x=xs[off];w=ws[off];
   for(j=1;j<n;j=j+1)begin @(negedge clk);x=xs[off+j];w=ws[off+j];end
   @(negedge clk);valid=0;#1;
   if(overflow || acc!==p[i][120:89] || y!==p[i][128:121])$fatal(1,"MAC_REQUANT case%0d acc%0d expected%0d y%0d expected%0d overflow%0d",i,acc,$signed(p[i][120:89]),y,p[i][128:121],overflow);
  end
  for(i=0;i<NMERGE;i=i+1)begin
   a=mp[i][7:0];b=mp[i][15:8];za=mp[i][23:16];zb=mp[i][31:24];zo=mp[i][39:32];ma=mp[i][71:40];mb=mp[i][103:72];ea=mp[i][111:104];eb=mp[i][119:112];use_b=mp[i][120];#2;
   if(my!==mp[i][128:121])$fatal(1,"MERGE case%0d y%0d expected%0d",i,my,mp[i][128:121]);
  end
  for(i=0;i<NROUND;i=i+1)begin rx=rp[i][63:0];rsh=rp[i][72:64];#2;if(ry!==rp[i][136:73])$fatal(1,"ROUND case%0d got%0d expected%0d",i,ry,$signed(rp[i][136:73]));end
  $display("PASS MAC_REQUANT=%0d MERGE=%0d ROUND=%0d SAMPLES=%0d",NCASES,NMERGE,NROUND,NSAMPLES);$finish;
 end
endmodule
'''
tb=tb.replace('module testbench;',f'module testbench;\n localparam NCASES={len(params)},NSAMPLES={len(xs)},NMERGE={len(merge)},NROUND={len(rounds)};')
(build/'testbench.sv').write_text(tb)
ctypes.windll.kernel32.SetErrorMode(0x8003)
runtime=ROOT/'external_runtime/icarus/mingw64';env=os.environ.copy();env['PATH']=str(runtime/'bin')+';C:\\mingw64\\bin;'+env.get('PATH','')
commands=[[str(runtime/'bin/iverilog.exe'),'-g2012','-B',str(runtime/'lib/ivl'),'-s','testbench','-o','units.vvp',str(HERE/'units.sv'),'testbench.sv'],[str(runtime/'bin/vvp.exe'),'-M',str(runtime/'lib/ivl'),'units.vvp']]
logs=[]
for command in commands:
 r=subprocess.run(command,cwd=build,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=90)
 logs.append({'command':command,'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr});print(r.stdout+r.stderr,flush=True)
 if r.returncode:
  (HERE/'failure.json').write_text(json.dumps(logs,indent=1));raise SystemExit(r.returncode)
assert 'PASS MAC_REQUANT=' in logs[-1]['stdout']
files={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [HERE/'units.sv',HERE/'verify.py',build/'testbench.sv',build/'params.mem',build/'xs.mem',build/'ws.mem',build/'merge.mem',build/'round.mem']}
record={'time':datetime.datetime.now().astimezone().isoformat(),'status':'MEASURED Icarus13 arithmetic-unit functional simulation PASS','pack_sha256':hashlib.sha256(pack.read_bytes()).hexdigest(),'conv_descriptors_covered':len(g.c),'conv_output_channels_per_descriptor':2,'mac_requant_cases':len(params),'scalar_mac_samples':len(xs),'merge_cases':len(merge),'round_boundary_cases':len(rounds),'oracle':'Independent Python fractions.Fraction round-half-even; uses actual selected package constants, no int_ref arithmetic helper','files':files,'logs':logs,'scope':'Sampled scalar MAC accumulation, conv requantization, add/cat input rescale and signed RNE boundaries ONLY. Not full network RTL, convolution addressing, descriptor loader, DDR3, camera/display, synthesis, timing, resource use or board fps. Testbench clock is a simulation schedule, not achievable clock evidence.','art_accepted':False,'FPGA_full_network_verified':False}
(HERE/'simulation_result.json').write_text(json.dumps(record,indent=1));(ROOT/'deployment_refine6000/rtl_math_verification.json').write_text(json.dumps(record,indent=1))
(HERE/'cases.json').write_text(json.dumps({'conv_cases':case_map,'merge_cases':merge_map},indent=1))
print(json.dumps({k:v for k,v in record.items() if k not in ('files','logs')},indent=1))
