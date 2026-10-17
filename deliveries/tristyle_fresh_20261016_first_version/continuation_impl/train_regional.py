"""Bounded last art experiment: local16/32px artwork co-occurrence, never global Gram.

Keeps the actual deployable model unchanged. The already-exporting6000 baseline
is preserved. This candidate must win actual17-scene/video review before selection.
"""
import json,pathlib,sys
import numpy as np
from PIL import Image
import torch
from torch.nn import functional as F
import train_art as base

ROOT=pathlib.Path(__file__).resolve().parents[1]
scale=6.
if '--regional-art-scale' in sys.argv:
    i=sys.argv.index('--regional-art-scale');scale=float(sys.argv[i+1]);del sys.argv[i:i+2]
run=sys.argv[sys.argv.index('--run')+1]
dest=ROOT/'runs'/run;dest.mkdir(parents=True,exist_ok=True)
(dest/'regional_config.json').write_text(json.dumps({'regional_art_scale':scale,'features':'VGG relu2/relu3,16 fixed sampled channels',
    'spatial_patch':'8x8 feature windows (~16/32 input pixels), stride8;48 highest-contrast reference regions per crop',
    'matching':'nearest normalized local covariance; reconstruct actual-art local co-occurrence; no global Gram statistic',
    'inference':'unchanged bare neural model, no new parameter or op','source':'continuation_impl/train_regional.py'},indent=2))

def desc(f,rms,count=None):
    channels=torch.linspace(0,f.shape[1]-1,16,device=f.device).long()
    v=f[:,channels].float()/rms[None,:,None,None]
    u=F.unfold(v,8,stride=8).reshape(v.shape[0],16,64,-1).permute(0,3,1,2)
    energy=u.var(-1,unbiased=False).mean(-1)
    gram=(u@u.transpose(-1,-2))/64
    gram=gram.flatten(-2)
    if count is not None and gram.shape[1]>count:
        ids=torch.randperm(gram.shape[1],device=f.device)[:count];gram=gram[:,ids]
    return gram,energy

OriginalBank=base.ArtBank
class RegionalArtBank(OriginalBank):
    def __init__(self,vgg,dev):
        super().__init__(vgg,dev);self.regional={}
        for style in base.STYLES:
            b=self.bank[style];rms=[]
            for j in (1,2):
                C=b['mean'][j].numel();ids=torch.linspace(0,C-1,16,device=dev).long()
                rms.append((b['mean'][j][ids].square()+b['std'][j][ids].square()).sqrt().clamp_min(1.))
            values=[[],[]]
            for row in self.refs[style]:
                im=Image.open(ROOT/row['path']).convert('RGB');w,h=im.size
                if style=='ink' and h>w*2:im=im.crop((int(w*.12),int(h*.05),int(w*.88),int(h*.95)))
                r=320/min(im.size);im=im.resize((round(im.width*r),round(im.height*r)),Image.Resampling.LANCZOS)
                for pos in (.25,.65):
                    l,t=round((im.width-256)*pos),round((im.height-256)*pos)
                    a=np.array(im.crop((l,t,l+256,t+256)),copy=True)
                    x=torch.from_numpy(a).permute(2,0,1)[None].float().to(dev)/255
                    with torch.no_grad(),torch.autocast('cuda',enabled=dev=='cuda'):fs=vgg(x)
                    for k,j in enumerate((1,2)):
                        g,e=desc(fs[j],rms[k]);ids=e[0].topk(min(48,e.shape[1])).indices
                        values[k].append(g[0,ids].detach())
            self.regional[style]={'rms':rms,'grams':[torch.cat(v) for v in values]}
            print('REGIONAL_BANK',style,[list(g.shape) for g in self.regional[style]['grams']],flush=True)
    def losses(self,fs,style):
        patch,moment=super().losses(fs,style);r=self.regional[style];local=patch.new_zeros(())
        for k,j in enumerate((1,2)):
            u,_=desc(fs[j],r['rms'][k],96);bank=r['grams'][k]
            with torch.no_grad():ids=(F.normalize(u.detach(),dim=-1)@F.normalize(bank,dim=-1).T).argmax(-1)
            local=local+F.smooth_l1_loss(u,bank[ids])
        return patch+scale*local,moment

base.ArtBank=RegionalArtBank
base.main()
