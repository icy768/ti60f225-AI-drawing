"""FP32 paired-objective and cross-image gradient diagnostics, no training."""
from pathlib import Path
import json,sys
import numpy as np
import torch
from torch.nn import functional as F
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(Path(__file__).parent))
from fit_capacity import Pairs,model_for_state,old,sha,now,sobel_target_loss

def cos(a,b):return float(F.cosine_similarity(a,b,dim=0,eps=1e-10))

def main():
    torch.set_num_threads(3);dev='cuda';out=ROOT/'reports/paired_v5/P1b/paired_gradient_conflicts_01';assert not out.exists();out.mkdir(parents=True)
    ds=Pairs('train',64);vgg=old.VGG().to(dev).eval();results=[]
    for label,path in [('V3',ROOT/'baseline/tristyle_v3_fp32.pt'),('paired64_planloss',ROOT/'experiments/paired_v5/p1b_uk_planloss_01/step_001500.pt'),('one_image_fit',ROOT/'experiments/paired_v5/p1b_uk_oneimage_01/step_001500.pt')]:
        state=torch.load(path,map_location='cpu',weights_only=False)['model'];m=model_for_state(state).to(dev).eval();m.load_state_dict(state)
        for n,p in m.named_parameters():p.requires_grad_(n.startswith('experts.1.'))
        named=[(n,p) for n,p in m.named_parameters() if p.requires_grad];params=[p for _,p in named];rows=[];vectors=[];group_norm=[]
        for stem,x,t,pr in ds.rows[:8]:
            h,w=x.shape[-2:];top,left=(h-256)//2,(w-256)//2;x=x[:,top:top+256,left:left+256][None].to(dev);t=t[:,top:top+256,left:left+256][None].to(dev)
            with torch.no_grad():features=m.encode(x);ft=vgg(t)
            raw=m.experts[1](*features);y=raw.clamp(0,1)*.98+raw*.02;fy=vgg(y)
            terms={'pixel':F.l1_loss(y,t)*1.5,'coarse':F.l1_loss(F.avg_pool2d(y,8),F.avg_pool2d(t,8))*1.5,'target_guide':sum(F.l1_loss(fy[j],ft[j]) for j in (1,2,3))*.1,'target_sobel':sobel_target_loss(y,t)*.5}
            gs={};norms={}
            for key,l in terms.items():
                grad=torch.autograd.grad(l,params,retain_graph=True);gs[key]=torch.cat([z.flatten() for z in grad]);assert torch.isfinite(gs[key]).all();norms[key]=float(gs[key].norm())
            total=sum(gs.values());vectors.append(total.detach());pairs={f'{a}__{b}':cos(gs[a],gs[b]) for a,b in [('pixel','target_guide'),('pixel','coarse'),('pixel','target_sobel'),('coarse','target_guide')]}
            parts={};cursor=0
            for name,p in named:
                n=p.numel();v=total[cursor:cursor+n];cursor+=n;group=name.split('.')[2];parts[group]=parts.get(group,0.)+float(v.square().sum())
            all_squared=float(total.square().sum());fractions={k:v/max(all_squared,1e-20) for k,v in parts.items()}
            group_norm.append(fractions);rows.append({'scene':stem,'box':[left,top,left+256,top+256],'weighted_losses':{k:float(v.detach()) for k,v in terms.items()},'gradient_norms':norms,'within_image_gradient_cosines':pairs,'total_gradient_squared_fraction_by_stage':fractions,'source':pr})
        matrix=[[cos(a,b) for b in vectors] for a in vectors];off=[matrix[i][j] for i in range(8) for j in range(i+1,8)];mean_grad=torch.stack(vectors).mean(0)
        results.append({'checkpoint':label,'checkpoint_sha256':sha(path),'rows':rows,'cross_image_cosines':matrix,'cross_image_mean_cosine':float(np.mean(off)),'negative_image_pairs':sum(v<0 for v in off),'image_pairs':len(off),'norm_of_mean_over_mean_norm':float(mean_grad.norm()/torch.stack([v.norm() for v in vectors]).mean()),'mean_stage_gradient_squared_fractions':{k:float(np.mean([r.get(k,0.) for r in group_norm])) for k in group_norm[0]}})
    result={'time':now(),'source_sha256':sha(__file__),'training_performed':False,'protocol':'first8 of original64 train images, fixed center256, FP32, expert1 only; paired UK PLAN losses. Checkpoint and source hashes retained','limitations':['Gradient conflict can be normal in minibatch learning; not proof of an impossible objective','Different parameterizations and checkpoints change cosine/norms; no artistic acceptance from these values','Cannot diagnose target quality or unique cause of multi-image failure alone'],'results':results}
    (out/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps([{'checkpoint':r['checkpoint'],'cross_image_mean_cosine':r['cross_image_mean_cosine'],'negative_image_pairs':r['negative_image_pairs'],'norm_of_mean_over_mean_norm':r['norm_of_mean_over_mean_norm'],'mean_stage_gradient_squared_fractions':r['mean_stage_gradient_squared_fractions'],'mean_pixel_guide_cosine':float(np.mean([x['within_image_gradient_cosines']['pixel__target_guide'] for x in r['rows']]))} for r in results],indent=2),flush=True)
if __name__=='__main__':main()
