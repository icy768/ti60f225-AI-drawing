"""Regress AE metering, held CDC snapshots and the shared APB/I2C interface."""
from pathlib import Path
import hashlib, json, os, subprocess

ROOT = Path(__file__).resolve().parent
BIN = Path(os.environ.get('ICARUS_BIN', ROOT.parent / 'tools/iverilog/mingw64/bin'))
OUT = ROOT / 'validation/main_ae'
OUT.mkdir(parents=True, exist_ok=True)
cases = {
    'meter': ['sim/main_ae_tb.v', 'rtl/sc_camera_rgb.v'],
    'meter_full': ['sim/main_ae_tb.v', 'rtl/sc_camera_rgb.v'],
    'apb': ['sim/apb_regs_tb.v', 'rtl/sc_apb_regs.v', 'rtl/sc431hai/i2c_reg16.v'],
}
results = {}
for name, sources in cases.items():
    exe = OUT / (name + '.vvp')
    params = ['-Ptb.'+k+'='+str(v) for k,v in dict(IW=1920,IH=1080,OW=640,OH=480,N=5400).items()] if name=='meter_full' else []
    subprocess.run([str(BIN/'iverilog.exe'), '-g2012', '-s', 'tb', *params, '-o', str(exe), *sources], cwd=ROOT, check=True)
    p = subprocess.run([str(BIN/'vvp.exe'), str(exe)], cwd=ROOT, capture_output=True, text=True, errors='replace')
    (OUT/(name+'.log')).write_text(p.stdout+p.stderr, encoding='utf-8')
    print(p.stdout, flush=True)
    assert p.returncode == 0 and 'PASS' in p.stdout
    results[name] = dict(passed=True, source_sha256={s: hashlib.sha256((ROOT/s).read_bytes()).hexdigest() for s in sources})
(OUT/'result.json').write_text(json.dumps(dict(passed=True, tests=results), indent=2)+'\n', encoding='utf-8')
