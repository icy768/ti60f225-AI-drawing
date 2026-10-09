from pathlib import Path
import subprocess,json
ROOT=Path(__file__).resolve().parent
S=ROOT/'validation/camera_sim';S.mkdir(exist_ok=True)
BIN=Path(__import__('os').environ.get('ICARUS_BIN',ROOT.parent/'tools/iverilog/mingw64/bin'))
gamma=[int(x,16)>>2 for x in (ROOT/'model/camera_gamma.mem').read_text().split()]
from sim_camera_mhc import expected as mhc_expected
expected=list(mhc_expected(24,20,8,6,7,gamma))
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
(S/'result.json').write_text(json.dumps(dict(passed=True,tests=tests),indent=2),encoding='utf-8',newline='\n')
