"""CPU-only input Jacobian diagnostic, never an artistic/capacity gate."""
from pathlib import Path
import json,sys
import numpy as np
import torch
from torch.nn import functional as F
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(Path(__file__).parent))
from fit_capacity import image_tensor,model_for_state,apply_architecture,sha,now

def main():
    torch.set_num_threads(3)
    manifest=json.loads((ROOT/'experiments/paired_v5/p1b_uk_fit_01/data_manifest.json').read_text())
    rows=manifest['train'][:3]
    checkpoints=[('V3',ROOT/'baseline/tristyle_v3_fp32.pt'),('PLAN_loss1500',ROOT/'experiments/paired_v5/p1b_uk_planloss_01/step_001500.pt'),('dilation2_1500',ROOT/'experiments/paired_v5/p1b_uk_dilation2_01/step_001500.pt'),('fullrecipe3000',ROOT/'experiments/paired_v5/p1diag_uk_fullrecipe_ampfix_01/step_003000.pt')]
    out=ROOT/'reports/paired_v5/P1b/receptive_field_01';out.mkdir(parents=True,exist_ok=True);records=[]
    for label,p in checkpoints:
        ck=torch.load(p,map_location='cpu',weights_only=False);model=model_for_state(ck['model']);model.load_state_dict(ck['model']);apply_architecture(model,ck.get('config',{}).get('expert1_s8_depthwise_dilation',1)==2);model.eval().requires_grad_(False)
        maps=[]
        for row in rows:
            ip=Path(row['input']);assert sha(ip)==row['input_sha256'];x=image_tensor(ip);x=F.interpolate(x[None],(256,256),mode='bilinear',align_corners=False,antialias=True).requires_grad_(True)
            y=model(x,1);energy=torch.zeros((256,256))
            for c in range(3):
                grad=torch.autograd.grad(y[0,c,128,128],x,retain_graph=c<2)[0][0];energy+=grad.abs().sum(0)
            e=energy.numpy().astype('float64');total=float(e.sum());assert total>0
            e/=total;yy,xx=np.mgrid[:256,:256];radius=np.sqrt((yy-128)**2+(xx-128)**2);order=radius.ravel().argsort();cdf=np.cumsum(e.ravel()[order]);r=radius.ravel()[order]
            rec={'checkpoint':label,'checkpoint_sha256':sha(p),'input':str(ip),'input_sha256':sha(ip),'scalar_outputs':'sum of absolute input Jacobians for3 output channels at128,128','view':'whole frame resized256square diagnostic only','r50_px':float(r[np.searchsorted(cdf,.5)]),'r90_px':float(r[np.searchsorted(cdf,.9)]),'r99_px':float(r[np.searchsorted(cdf,.99)]),'absolute_jacobian_sum':total,'mass_beyond64_px':float(e[radius>64].sum()),'mass_beyond100_px':float(e[radius>100].sum())};records.append(rec)
            z=np.log1p(e/e.max()*1000)/np.log(1001);im=Image.fromarray((z*255).round().astype('uint8'));im.save(out/f'{label}_{ip.stem}_jacobian.png');maps.append(im.convert('RGB'))
        sheet=Image.new('RGB',(768,278),'white');d=ImageDraw.Draw(sheet)
        for i,im in enumerate(maps):sheet.paste(im,(i*256,0));d.text((i*256+2,258),label+' '+rows[i]['stem'],fill='black')
        sheet.save(out/f'{label}_summary.jpg',quality=94)
    (out/'result.json').write_text(json.dumps({'time':now(),'source_sha256':sha(__file__),'CPU_only':True,'training_performed':False,'limitations':'3 prespecified TRAIN inputs, one output location after square resize; local Jacobian depends on activations and is not a proof of capacity/semantics or full theoretical RF. No artwork gate inferred.','records':records},indent=2));print(json.dumps([{k:r[k] for k in ('checkpoint','r50_px','r90_px','r99_px','mass_beyond64_px')} for r in records]))
if __name__=='__main__':main()
