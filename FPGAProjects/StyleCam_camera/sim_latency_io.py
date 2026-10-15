from pathlib import Path
import subprocess,json,hashlib
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'validation/latency_io';OUT.mkdir(exist_ok=True)
BIN=ROOT.parent/'tools/iverilog/mingw64/bin'
rtl=['sc_replay','sc_async_fifo']
exe=OUT/'replay.vvp'
subprocess.run([str(BIN/'iverilog.exe'),'-g2012','-s','tb','-o',str(exe),'sim/latency_replay_tb.v',*[f'rtl/{f}.v' for f in rtl]],cwd=ROOT,check=True)
p=subprocess.run([str(BIN/'vvp.exe'),str(exe)],cwd=ROOT,capture_output=True,text=True)
(OUT/'simulation.log').write_text(p.stdout+p.stderr);print(p.stdout,flush=True)
assert p.returncode==0 and 'PASS replay four banks' in p.stdout
(OUT/'result.json').write_text(json.dumps(dict(passed=True,pixels_exact=4096,input_banks=4,asynchronous_clocks=True,
    source_sha256={f'rtl/{f}.v':hashlib.sha256((ROOT/f'rtl/{f}.v').read_bytes()).hexdigest() for f in rtl}),indent=2))
