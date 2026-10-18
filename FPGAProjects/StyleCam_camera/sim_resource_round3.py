"""Peripheral resource pass 3: native font model and complete HDMI equivalence."""
from pathlib import Path
import hashlib, json, os, subprocess, sys

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'validation/resource_opt_round3_20261016/simulation'
OUT.mkdir(parents=True,exist_ok=True)
BIN=Path(os.environ.get('ICARUS_BIN',ROOT.parent/'tools/iverilog/mingw64/bin'))
vendor=Path(os.environ.get('STYLECAM_EFINITY','D:/ELS/efinity/2026.1'))/'sim_models/verilog/efx_dpram10.v'
cases={
 'font_behavior':(['sim/resource_font_tb.v'],[]),
 'font_primitive':(['sim/resource_font_tb.v',str(vendor)],['-DSYNTHESIS']),
 'display_equivalence':(['sim/resource_display_tb.v','sim/reference/sc_display_resource2.v','rtl/sc_display.v','rtl/sc_async_fifo.v','rtl/common.v'],[]),
}
selected=set(sys.argv[1:]);assert selected.issubset(cases)
record=OUT/'result.json'
tests=json.loads(record.read_text())['tests'] if selected and record.exists() else {}
for name,(sources,options) in cases.items():
 if selected and name not in selected:continue
 exe=OUT/(name+'.vvp')
 subprocess.run([str(BIN/'iverilog.exe'),'-g2012','-s','tb',*options,'-o',str(exe),*sources],cwd=ROOT,check=True)
 p=subprocess.run([str(BIN/'vvp.exe'),str(exe)],cwd=ROOT,capture_output=True,text=True,errors='replace')
 (OUT/(name+'.log')).write_text(p.stdout+p.stderr,encoding='utf-8')
 print(name,p.stdout+p.stderr,flush=True)
 assert p.returncode==0 and 'PASS' in p.stdout,name
 inputs=[Path(s) for s in sources if not Path(s).is_absolute()]+[Path('rtl/sc_osd_font.vh'),Path('model/font8x16.mem')]
 tests[name]=dict(passed=True,source_sha256={s.as_posix():hashlib.sha256((ROOT/s).read_bytes()).hexdigest() for s in inputs})
 if name=='font_primitive':tests[name]['vendor_model_sha256']=hashlib.sha256(vendor.read_bytes()).hexdigest()
record.write_text(json.dumps(dict(passed=True,tests=tests),indent=2)+'\n',encoding='utf-8')
