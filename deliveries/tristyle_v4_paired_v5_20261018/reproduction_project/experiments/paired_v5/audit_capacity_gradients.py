"""Cross-check scaled AMP and FP32 component gradients without training."""
from pathlib import Path
import json,sys,random
import torch
from torch.nn import functional as F
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(Path(__file__).parent))
from fit_capacity import Pairs,old,model_for_state,sha,now

def main():
    torch.set_num_threads(3);dev='cuda';p=ROOT/'baseline/tristyle_v3_fp32.pt';state=torch.load(p,map_location='cpu',weights_only=False)['model'];m=model_for_state(state).to(dev);m.load_state_dict(state)
    for n,v in m.named_parameters():v.requires_grad_(n.startswith('experts.1.'))
    params=[v for v in m.parameters() if v.requires_grad];vgg=old.VGG().to(dev).eval();ds=Pairs('train',64);x,t=ds.batch(8,random.Random(20261097));x,t=x.to(dev),t.to(dev);rows=[];vectors={}
    for mode,amp,scale in [('FP32',False,1.),('AMP_UNSCALED',True,1.),('AMP_SCALED',True,65536.)]:
        with torch.autocast('cuda',dtype=torch.float16,enabled=amp):
            with torch.no_grad():features=m.encode(x);ft=vgg(t)
            raw=m.experts[1](*features).float();y=raw.clamp(0,1)*.98+raw*.02;fy=vgg(y);terms={'paired_L1':F.l1_loss(y,t),'target_perceptual':sum(F.l1_loss(fy[j].float(),ft[j].float()) for j in (1,2,3))*.1}
        for key,loss in terms.items():
            gs=torch.autograd.grad(loss*scale,params,retain_graph=True);vec=torch.cat([(g.float()/scale).flatten() for g in gs]);vectors[(mode,key)]=vec
            rows.append({'mode':mode,'term':key,'weighted_loss':float(loss.detach()),'gradient_l2':float(vec.norm()),'gradient_finite':bool(torch.isfinite(vec).all()),'scale':scale})
    comparisons={key:float(F.cosine_similarity(vectors[('FP32',key)],vectors[('AMP_SCALED',key)],dim=0)) for key in terms}
    result={'time':now(),'checkpoint':str(p),'checkpoint_sha256':sha(p),'source_sha256':sha(__file__),'training_performed':False,'data':'first original64 train batch with fixed seed; no fixed17','rows':rows,'FP32_vs_scaled_AMP_gradient_cosine':comparisons,'correction':'Original P1b autograd audits used unscaled FP16; zero norms are not actual training contribution. Training uses GradScaler.scale(loss).backward() correctly.'}
    dest=ROOT/'reports/paired_v5/P1b/gradient_precision_audit.json';dest.write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2),flush=True)
if __name__=='__main__':main()
