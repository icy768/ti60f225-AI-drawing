"""Resource pass 2: exhaustive camera/font math and peripheral equivalence."""
from pathlib import Path
import hashlib, json, os, subprocess, sys

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'validation/resource_opt_round2_20261016/simulation'
OUT.mkdir(parents=True,exist_ok=True)
BIN=Path(os.environ.get('ICARUS_BIN',ROOT.parent/'tools/iverilog/mingw64/bin'))
cases={
 'math':(['sim/camera_math_tb.v','rtl/sc_camera_rgb.v'],[]),
 'gamma':(['sim/camera_gamma_tb.v','rtl/sc_camera_rgb.v'],[]),
 'apb_equivalence':(['sim/resource_apb_tb.v','sim/reference/sc_apb_regs_resource1.v','rtl/sc_apb_regs.v','rtl/sc431hai/i2c_reg16.v'],[]),
 'replay_equivalence':(['sim/resource_replay_tb.v','sim/reference/sc_replay_resource1.v','rtl/sc_replay.v','rtl/sc_async_fifo.v'],[]),
 'replay_full':(['sim/resource_replay_tb.v','sim/reference/sc_replay_resource1.v','rtl/sc_replay.v','rtl/sc_async_fifo.v'],['-Ptb.PIXELS=307200']),
 'capture':(['sim/capture_tb.v','rtl/sc_capture.v','rtl/sc_async_fifo.v','rtl/sc_write_arbiter.v'],[]),
 'capture_mirror':(['sim/capture_tb.v','rtl/sc_capture.v','rtl/sc_async_fifo.v','rtl/sc_write_arbiter.v'],['-Ptb.MIRROR=1']),
 'display':(['sim/display_tb.v','rtl/sc_display.v','rtl/sc_async_fifo.v','rtl/common.v'],[]),
 'i2c_equivalence':(['sim/resource_i2c_tb.v','sim/reference/i2c_reg16_resource1.v','rtl/sc431hai/i2c_reg16.v'],[]),
 'i2c_actual_bounds':(['sim/resource_i2c_tb.v','sim/reference/i2c_reg16_resource1.v','rtl/sc431hai/i2c_reg16.v'],['-Ptb.TICK=1000','-Ptb.TIMEOUT=1000']),
}
selected=set(sys.argv[1:])
assert selected.issubset(cases), 'Unknown test case'
result=json.loads((OUT/'result.json').read_text())['tests'] if selected and (OUT/'result.json').exists() else {}
result={name:test for name,test in result.items() if name in cases}
for name,(sources,opts) in cases.items():
 if selected and name not in selected:continue
 exe=OUT/(name+'.vvp')
 subprocess.run([str(BIN/'iverilog.exe'),'-g2012','-s','tb',*opts,'-o',str(exe),*sources],cwd=ROOT,check=True)
 p=subprocess.run([str(BIN/'vvp.exe'),str(exe)],cwd=ROOT,capture_output=True,text=True,errors='replace')
 (OUT/(name+'.log')).write_text(p.stdout+p.stderr,encoding='utf-8')
 print(name,p.stdout+p.stderr,flush=True)
 assert p.returncode==0 and 'PASS' in p.stdout,name
 result[name]=dict(passed=True,source_sha256={s:hashlib.sha256((ROOT/s).read_bytes()).hexdigest() for s in sources})
(OUT/'result.json').write_text(json.dumps(dict(passed=True,tests=result),indent=2)+'\n',encoding='utf-8')
