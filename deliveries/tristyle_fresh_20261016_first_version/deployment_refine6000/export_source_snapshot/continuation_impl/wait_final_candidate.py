"""Deadline reserve: finish one existing train, then export/test candidate automatically.
Does not select an artistic winner or declare acceptance. Never starts a second trainer.
"""
import datetime,json,pathlib,subprocess,sys,time
ROOT=pathlib.Path(__file__).resolve().parents[1];run=ROOT/'runs/continuation_final_refine'
limit=datetime.datetime.fromisoformat('2026-10-17T08:12:00+08:00').timestamp()
record=ROOT/'supervisor/reserve_pipeline_status.json'
record.write_text(json.dumps({'status':'waiting for existing refinement only','candidate':'runs/continuation_final_refine/step_006000.pt','deadline':limit},indent=2))
while not (run/'finished.json').exists() and time.time()<limit:
    if (run/'train.err.log').exists():
        err=(run/'train.err.log').read_text(encoding='utf-8',errors='replace')
        if 'Traceback (most recent call last)' in err:break
    time.sleep(15)
checkpoint='runs/continuation_final_refine/step_006000.pt'
if not (ROOT/checkpoint).exists():
    record.write_text(json.dumps({'status':'NOT STARTED:6000 candidate absent; supervisor must inspect existing actual checkpoints','time':datetime.datetime.now().astimezone().isoformat()},indent=2));raise SystemExit(1)
# finished.json is written after the last model save; wait for the trainer to release CUDA.
time.sleep(5)
args=[sys.executable,'-u','continuation_impl/delivery_pipeline.py','--checkpoint',checkpoint,'--out','deployment_refine6000','--qat-steps','600','--qat-device','cuda','--robust-calibration','--native-video-frames','150','--fullres-video']
record.write_text(json.dumps({'status':'running candidate pipeline, artistic selection pending','command':args,'time':datetime.datetime.now().astimezone().isoformat()},indent=2))
with (ROOT/'runs/final_reserve_pipeline.log').open('w',encoding='utf-8') as f:r=subprocess.run(args,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
record.write_text(json.dumps({'status':'pipeline finished; independent visual acceptance still required','returncode':r.returncode,'time':datetime.datetime.now().astimezone().isoformat()},indent=2))
raise SystemExit(r.returncode)
