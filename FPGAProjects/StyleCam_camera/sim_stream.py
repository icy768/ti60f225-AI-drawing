"""Preview RTL regression: small raster, forced FIFO overflow recovery, real 1080p60 timing."""
from pathlib import Path
import os, subprocess, json
ROOT = Path(__file__).resolve().parent
OUT = ROOT/'validation/creative_review'
OUT.mkdir(exist_ok=True)
BIN = Path(os.environ.get('IVERILOG_BIN', ROOT.parent/'tools/iverilog/mingw64/bin'))
sources = ['sim/stream_link_tb.v', 'rtl/sc_stream_tap.v', 'rtl/sc_stream_link.v', 'rtl/sc_async_fifo.v', 'rtl/uart_byte.v']
results = {}
for name, opts in [('small', []), ('recovery', ['-Pstream_link_tb.RECOVERY=1']), ('1080p60', ['-Pstream_link_tb.FULL_SIZE=1'])]:
    exe = OUT/(name+'.vvp')
    subprocess.run([str(BIN/'iverilog.exe'), '-g2012', '-s', 'stream_link_tb', *opts, '-o', str(exe), *sources], cwd=ROOT, check=True)
    print('Running', name, flush=True)
    r = subprocess.run([str(BIN/'vvp.exe'), str(exe)], cwd=ROOT, capture_output=True, text=True)
    (OUT/(name+'.log')).write_text(r.stdout+r.stderr, encoding='utf-8')
    print(r.stdout+r.stderr, flush=True)
    assert r.returncode == 0 and 'PASS tap' in r.stdout and 'FAIL' not in r.stdout
    results[name] = {'passed': True, 'log': r.stdout}
(OUT/'stream_result.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
