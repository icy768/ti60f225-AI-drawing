"""Full64 and full validation L1 baseline/control audit; no artistic gate by score."""
from pathlib import Path
import argparse,json,sys
import numpy as np
import torch
from torch.nn import functional as F
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(Path(__file__).parent))
from fit_capacity import Pairs,model_for_state,sha,now,apply_architecture,apply_nonlinear_mixer

@torch.no_grad()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--run',default='p1b_uk_fit_01');args=ap.parse_args();torch.set_num_threads(3);dev='cuda'
    base_path=ROOT/'baseline/tristyle_v3_fp32.pt';cand_path=ROOT/'experiments/paired_v5'/args.run/'step_001500.pt'
    nets=[]
    for p in (base_path,cand_path):
        ck=torch.load(p,map_location='cpu',weights_only=False);state=ck['model'];m=model_for_state(state)
        if ck.get('config',{}).get('expert1_nonlinear_mixer',False):apply_nonlinear_mixer(m)
        m=m.to(dev).eval();m.load_state_dict(state);apply_architecture(m,ck.get('config',{}).get('expert1_s8_depthwise_dilation',1)==2);nets.append(m)
    rows=[]
    for split,limit in [('train',64),('validation',10000)]:
        ds=Pairs(split,limit)
        for stem,x,t,provenance in ds.rows:
            h,w=x.shape[-2:];z=F.pad(x[None].to(dev),(0,-w%8,0,-h%8),mode='replicate');tt=t.to(dev);values=[]
            for m in nets:
                y=m(z,1)[0,:,:h,:w].float().clamp(0,1);values.append(float((y-tt).abs().mean()))
            rows.append({'split':split,'scene':stem,'V3_target_L1':values[0],'student_target_L1':values[1],**provenance})
    summary={s:{'count':len([r for r in rows if r['split']==s]),**{key:float(np.mean([r[key] for r in rows if r['split']==s])) for key in ('V3_target_L1','student_target_L1')}} for s in ('train','validation')}
    for v in summary.values():v['relative_L1_reduction_percent']=(1-v['student_target_L1']/v['V3_target_L1'])*100
    out=ROOT/'reports/paired_v5/P1b'/args.run;out.mkdir(parents=True,exist_ok=True)
    (out/'full_split_baseline.json').write_text(json.dumps({'time':now(),'baseline_checkpoint':str(base_path),'baseline_sha256':sha(base_path),'student_checkpoint':str(cand_path),'student_sha256':sha(cand_path),'protocol':'native lossless input, replicate to multiple8, clipped FP32 student vs exact ukiyoe_p1 target; unweighted per-scene RGB MAE','timing_note':'Full64 baseline requirement arrived after P1b started; baseline measured retrospectively from immutable original checkpoint, before followup intervention','artistic_gate_passed':False,'summary':summary,'rows':rows},indent=2));print(json.dumps(summary),flush=True)
if __name__=='__main__':main()
