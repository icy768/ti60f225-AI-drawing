"""Single sequential P5 pipeline: 03:00 freeze -> QAT600 -> fixed17 retention.

No model training begins until the owner and scheduled freeze have been checked.
This parent is CPU-only; only its QAT child uses CUDA. Do not start duplicate jobs.
"""
from pathlib import Path
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
P5=ROOT/'reports/paired_v5/P5'
DEPLOY='deployment/paired_v5_qat600_01'
VALIDATION='reports/paired_v5/P5/retention_01'
ZONE=dt.timezone(dt.timedelta(hours=8))


def now():return dt.datetime.now(ZONE).isoformat()


def owner():
    return json.loads(Path('D:/ClaudeTest/guidance/OWNER.json').read_text(encoding='utf-8-sig'))['owner']


def record(phase, pid=None, **extra):
    state={'time':now(),'phase':'P5 / '+phase,'run':DEPLOY,'step':0,'pid':pid,
           'owner':'codex','gate':'G2_FAIL_ART_AND_UK_NATIVE_WARP','promoted':False,
           'pipeline_pid':os.getpid(),**extra}
    (ROOT/'STATE.json').write_text(json.dumps(state,indent=2),encoding='utf-8')
    (P5/'PIPELINE.json').write_text(json.dumps(state,indent=2),encoding='utf-8')


def run(label,args):
    assert owner()=='codex','Ownership changed before next pipeline stage; do not start duplicate work'
    with (ROOT/f'logs/p5_{label}.out.log').open('w',encoding='utf8') as stdout, (ROOT/f'logs/p5_{label}.err.log').open('w',encoding='utf8') as stderr:
        process=subprocess.Popen([sys.executable,*args],cwd=ROOT,stdout=stdout,stderr=stderr)
        record(label,process.pid,command=[sys.executable,*args])
        code=process.wait()
        assert code==0,f'{label} failed exit={code}; preserve outputs and inspect logs'


def main():
    assert owner()=='codex'
    assert not (P5/'PIPELINE.json').exists(),'Pipeline already created; inspect it before any resume'
    record('waiting_for_0300')
    threshold=dt.datetime(2026,10,18,3,0,tzinfo=ZONE)
    while dt.datetime.now(ZONE)<threshold:time.sleep(2)
    assert owner()=='codex'
    prepared=json.loads((P5/'FREEZE_PREPARED.json').read_text(encoding='utf-8-sig'))
    checkpoint=ROOT/prepared['checkpoint']
    assert hashlib.sha256(checkpoint.read_bytes()).hexdigest()==prepared['checkpoint_sha256']
    assert all(v['all_exact'] for v in prepared['unchanged_experts'].values())
    assert not (P5/'FREEZE.json').exists(),'Existing freeze requires manual review'
    prepared.update(frozen=True,frozen_at=now(),guidance_sha256=hashlib.sha256(Path('D:/ClaudeTest/guidance/LATEST.md').read_bytes()).hexdigest())
    (P5/'FREEZE.json').write_text(json.dumps(prepared,indent=2),encoding='utf-8')
    (P5/'pipeline_source.py').write_bytes(Path(__file__).read_bytes())
    run('qat600',['experiments/paired_v5/p5_preserve_qat.py','--checkpoint',prepared['checkpoint'],
                  '--freeze-record','reports/paired_v5/P5/FREEZE.json','--out',DEPLOY])
    run('retention',['experiments/paired_v5/p5_validate.py','--deployment',DEPLOY,'--out',VALIDATION])
    record('qat_and_retention_complete',step=600,validation=VALIDATION)


if __name__=='__main__':
    try:main()
    except Exception as error:
        (P5/'PIPELINE_ERROR.json').write_text(json.dumps({'time':now(),'error':repr(error),'pipeline_pid':os.getpid()},indent=2),encoding='utf-8')
        raise
