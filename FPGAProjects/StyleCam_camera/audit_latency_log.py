"""Check a RISCV10 serial capture after manual download; never touches hardware.

Capture at least 30 seconds after calibration, and switch among all three styles.
Total skip includes startup calibration; steady-state acceptance uses increments.
"""
import argparse,json,re
from pathlib import Path
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('log',type=Path)
ap.add_argument('--output',type=Path);args=ap.parse_args()
text=args.log.read_text(encoding='utf-8',errors='replace')
assert re.search(r'ID=(?:0x)?53430[aA]0[aA]\b',text),'Capture must include the RISCV10 boot ID'
samples=[];perfs=[]
for line in text.splitlines():
    row={k:float(v) if '.' in v else int(v) for k,v in re.findall(r'(\w+)=([0-9]+(?:\.[0-9]+)?)',line)}
    stamp=re.search(r'\[(\d+) ms\]',line)
    if stamp and int(stamp[1])>0 and row.get('ready')==7 and 'run_skip' in row:
        row['time_ms']=int(stamp[1]);samples.append(row)
    if line.startswith('perf ') and 'scan_sw_max_us' in row:perfs.append(row)
assert len(samples)>=10 and samples[-1]['time_ms']-samples[0]['time_ms']>=30000,'Need 30 seconds of periodic steady-state status'
assert set(s['style'] for s in samples)=={0,1,2},'Exercise all three styles'
for key in ['skip','run_skip','caperr','vid_err','hdmi_err','irq_err']:
    assert all(s[key]==samples[0][key] for s in samples),f'{key} increased during steady-state capture'
assert all(s['uf']==0 for s in samples),'HDMI underflow'
assert all(s['fps']>=29.0 and s['nn_ms']<33.3 for s in samples),'Steady-state service rate below target'
assert perfs and 0<max(s['scan_sw_max_us'] for s in perfs)<100000,'No measured switch or switch exceeded 100 ms'
report=dict(passed=True,scope='captured board interval only',log=str(args.log.resolve()),
    duration_ms=samples[-1]['time_ms']-samples[0]['time_ms'],samples=len(samples),styles=[0,1,2],
    steady_skipped_delta=samples[-1]['skip']-samples[0]['skip'],
    fps_min=min(s['fps'] for s in samples),nn_ms_max=max(s['nn_ms'] for s in samples),
    scan_switch_max_us=max(s['scan_sw_max_us'] for s in perfs))
print(json.dumps(report,ensure_ascii=False,indent=2))
if args.output:args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
