"""Exercise real four-bank capture and scheduling with an explicitly bounded engine.

Time scaled 100x; 1000 control ticks = 1 ms. This proves buffering/ordering under
the stated service budget, not hardware performance or actual DDR bandwidth.
"""
from pathlib import Path
import hashlib,json,subprocess,re
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'validation/latency_schedule';OUT.mkdir(exist_ok=True)
BIN=ROOT.parent/'tools/iverilog/mingw64/bin'
rtl=['sc_capture','sc_video_schedule','sc_async_fifo']
results=[]
for phase,gap in [(0,1160),(5500,1160),(11000,1160),(16666,1160),(5500,1300)]:
    label=f'phase_{phase}_gap_{gap}'
    exe=OUT/(label+'.vvp')
    subprocess.run([str(BIN/'iverilog.exe'),'-g2012','-s','tb',f'-Ptb.VPHASE={phase}',f'-Ptb.PAIR_GAP={gap}',
        '-o',str(exe),'sim/latency_schedule_tb.v',*[f'rtl/{f}.v' for f in rtl]],cwd=ROOT,check=True)
    run=subprocess.run([str(BIN/'vvp.exe'),str(exe)],cwd=ROOT,capture_output=True,text=True)
    (OUT/(label+'.log')).write_text(run.stdout+run.stderr,encoding='utf-8')
    print(run.stdout,flush=True)
    assert run.returncode==0 and 'PASS bounded scheduler' in run.stdout
    latency=int(re.search(r'max_switch_ticks=(\d+)',run.stdout)[1])/1000
    results.append(dict(hdmi_phase=phase,capture_span_ms=23*gap/1000,frames=100,service_budget_ms=32.0,skipped=0,max_switch_ms=latency,
        banks=int(re.search(r'banks=([0-9a-f]+)',run.stdout)[1],16)))
assert any(r['banks']==15 for r in results), 'Fourth bank not exercised'
(OUT/'result.json').write_text(json.dumps(dict(passed=True,hardware_verified=False,
    real_capture_and_scheduler_rtl=True,engine_is_bounded_behavioral_model=True,
    sensor_fps=1000000/33334,hdmi_fps=1000000/16667,tests=results,
    source_sha256={f'rtl/{f}.v':hashlib.sha256((ROOT/f'rtl/{f}.v').read_bytes()).hexdigest() for f in rtl}),indent=2),encoding='utf-8')
