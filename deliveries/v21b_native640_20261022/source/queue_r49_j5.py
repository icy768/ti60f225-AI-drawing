"""Finite serial research queue after explicit F0/preflight gates; no promotion."""
import os,sys,json,subprocess,datetime,time,hashlib
from pathlib import Path
R=Path(__file__).resolve().parent;Q=R/'QUEUE_R49_J5.json';P=R/'R44';P.mkdir(exist_ok=True)
def now():return datetime.datetime.now().astimezone().isoformat()
def put():s['updated_at']=now();Q.write_text(json.dumps(s,ensure_ascii=False,indent=2),encoding='utf-8')
s={'round':49,'items':[]}
jobs=[(f'J5_{term.upper()}','all','-1',['--joint','--vg-object-ab-weight','0.60','--j5-term',term,'--new-term-fraction','0.30'],1000,'1e-4') for term in ['vg']]
assert json.loads((R/'R49/PREFLIGHT.json').read_text(encoding='utf-8-sig'))['passed']
s.update(status='RUNNING',queue_pid=os.getpid(),items=[],auto_adopt=False,phase=1.0,observer=False,forward='r44_forward.TinyStyleNet',full_model_state=True,optimizer_restored=False,optimizer_missing_in_source=False,optimizer_note="independent branches with fresh Adam; parent optimizer not restored");put()
for ident,variant,sty,extra,steps,lr in jobs:
 t=datetime.datetime.now()
 if (t.hour,t.minute)>=(19,0):s['status']='CUTOFF_NO_NEW_RUN';put();break
 # USER: one GPU, no unrelated training starts; this queue is the sole GPU owner.
 run=f'runs/r49_{ident.lower()}';assert not (R/run).exists(), 'Never restart a completed run';log=P/f'{ident}.log'
 args=['--init','runs/r44_j1_60/student.pt','--variant',variant,'--affine-style',sty,'--steps',str(steps),'--batch','4','--crop','256','--lr',lr,'--seed','4400','--qat','--out',run]+extra
 item={'id':ident,'research_only':True,'start':now(),'steps':steps,'args':args,'log':str(log),'eta_seconds_estimate':240,'board_validated':False,'adopted':False}
 s['items'].append(item)
 with log.open('w',encoding='utf-8') as stream:
  proc=subprocess.Popen([sys.executable,'-X','utf8','-u','algo/train_art_styles_r49.py']+args,cwd=R,stdout=stream,stderr=subprocess.STDOUT)
  item['pid']=proc.pid;s['pid']=proc.pid;s['eta']='training estimate ~4min/run; actual from train.jsonl';put();item['training_rc']=proc.wait()
 s['pid']=None;put()
 if item['training_rc']!=0:item['status']='TRAIN_FAILED';s['status']='TRAIN_FAILED';put();break
 with (P/f'{ident}_export.log').open('w',encoding='utf-8') as stream:
  rc=subprocess.run([sys.executable,'-X','utf8','algo/export_frozen_qparams.py','--checkpoint',run+'/student.pt','--contract','audits/v21b_deploy_blob/qparams','--out',f'R44/{ident}_qparams'],cwd=R,stdout=stream,stderr=subprocess.STDOUT).returncode
 item['export_rc']=rc;put()
 if rc!=0:item['status']='EXPORT_FAIL_NO_SCALE_OVERRIDE';put();continue
 with (P/f'{ident}_eval.log').open('w',encoding='utf-8') as stream:
  proc=subprocess.Popen([sys.executable,'-X','utf8','-u','eval_r49.py','--id',ident,'--run',run,'--style',sty],cwd=R,stdout=stream,stderr=subprocess.STDOUT)
  s['pid']=proc.pid;put();item['eval_rc']=proc.wait();s['pid']=None
 item['status']='INTEGER_BLIND_READY_AWAIT_SUPERVISION' if item['eval_rc']==0 else 'EVAL_FAILED';item['end']=now();put()
 with (P/f'{ident}_fidelity.log').open('w',encoding='utf-8') as stream:
  item['fidelity_rc']=subprocess.run([sys.executable,'-X','utf8','r49_candidate_fidelity.py','--id',ident],cwd=R,stdout=stream,stderr=subprocess.STDOUT).returncode
 put()
else:s['status']='COMPLETE_AWAIT_VISUAL_REVIEW'
s['queue_pid']=None;s['pid']=None;s['eta']=None;put();print(s['status'],flush=True)
