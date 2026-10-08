from pathlib import Path
import subprocess,json
ROOT=Path(__file__).resolve().parent
S=ROOT/'validation/camera_sim';S.mkdir(exist_ok=True)
BIN=Path(__import__('os').environ.get('ICARUS_BIN',ROOT.parent/'tools/iverilog/mingw64/bin'))
gamma=[int(x,16)>>2 for x in (ROOT/'model/camera_gamma.mem').read_text().split()]
expected=[]
def raw(f,x,y):return (f*31+x*7+y*11)%240
def encode(v):return gamma[(v<<2)|(v>>6)]
for f in range(2):
 pixels=[]
 for y in range(4,16,2):
  for x in range(4,20,2):
   srcx=22-x
   r=encode(raw(f,srcx+1,y+1));b=encode(raw(f,srcx,y))
   gv=(raw(f,srcx+1,y)+raw(f,srcx,y+1)+1)//2
   g=encode(gv)
   pixels.append(r|(g<<8)|(b<<16))
 expected.extend(pixels[i]|(pixels[i+1]<<24) for i in range(0,48,2))
(S/'rgb_expected.hex').write_text('\n'.join(f'{v:012x}' for v in expected)+'\n',encoding='ascii')
tests={}
for name,files in {
 'camera_rgb':['sc_camera_rgb'],
 'capture':['sc_capture','sc_write_arbiter','sc_async_fifo'],
 'schedule':['sc_video_schedule','sc_button'],
 'display':['sc_display','sc_async_fifo','common'],
 'apb_regs':['sc_apb_regs','sc431hai/i2c_reg16']}.items():
 exe=S/(name+'.vvp')
 subprocess.run([str(BIN/'iverilog.exe'),'-g2012','-s','tb','-o',str(exe),str(ROOT/f'sim/{name}_tb.v'),*[str(ROOT/f'rtl/{f}.v') for f in files]],cwd=ROOT,check=True)
 r=subprocess.run([str(BIN/'vvp.exe'),str(exe)],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace')
 (S/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8');print(r.stdout,flush=True)
 assert r.returncode==0 and 'PASS' in r.stdout,r.stdout+r.stderr
 tests[name]=dict(passed=True,log=str(S/(name+'.log')))
(S/'result.json').write_text(json.dumps(dict(passed=True,tests=tests),indent=2),encoding='utf-8')
