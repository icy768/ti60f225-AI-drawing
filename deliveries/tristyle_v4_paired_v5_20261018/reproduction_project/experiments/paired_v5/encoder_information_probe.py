"""Read-only test of information retained by the frozen V3 shallow encoder.

A linear RGB readout is a diagnostic, not a new deployed network. It neither
proves nonlinear information loss nor sufficient artistic capacity.
"""
from pathlib import Path
import json,sys
import numpy as np
import torch
from torch.nn import functional as F
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(Path(__file__).parent))
from fit_capacity import Pairs,model_for_state,sha,now

@torch.no_grad()
def main():
    torch.set_num_threads(3);dev='cuda';out=ROOT/'reports/paired_v5/P1b/encoder_information_01';assert not out.exists();out.mkdir(parents=True)
    p=ROOT/'baseline/tristyle_v3_fp32.pt';state=torch.load(p,map_location='cpu',weights_only=False)['model'];model=model_for_state(state).to(dev).eval();model.load_state_dict(state)
    train=Pairs('train',64);val=Pairs('validation',12);features=[];colors=[];activity=[[] for _ in range(4)]
    def encode(x):
        x=F.interpolate(x[None],size=(256,256),mode='bilinear',align_corners=False,antialias=True).to(dev);fs=model.encode(x)
        return x,fs
    for stem,x,t,pr in train.rows[:32]:
        z,fs=encode(x);f=fs[0][0,:,4:-4,4:-4].flatten(1).T;y=z[0,:,4:-4,4:-4].flatten(1).T
        ids=torch.linspace(0,len(f)-1,1024,device=dev).round().long();features.append(f[ids].cpu());colors.append(y[ids].cpu())
        for j,v in enumerate(fs):activity[j].append({'scene':stem,'zero_fraction_by_channel':(v==0).float().mean((0,2,3)).cpu().tolist(),'rms_by_channel':v.square().mean((0,2,3)).sqrt().cpu().tolist()})
    A=torch.cat(features).double();B=torch.cat(colors).double();A=torch.cat((A,torch.ones(len(A),1,dtype=A.dtype)),1)
    # CPU SVD least squares; no neural-network or expert weight update.
    solve=torch.linalg.lstsq(A,B,driver='gelsd');coef=solve.solution.float().to(dev);singular=solve.singular_values.tolist();rows=[]
    for split,ds in [('train_heldout32',train.rows[32:]),('validation12',val.rows)]:
        for idx,(stem,x,t,pr) in enumerate(ds):
            z,fs=encode(x);f=fs[0].permute(0,2,3,1);design=torch.cat((f,torch.ones_like(f[...,:1])),-1);raw=(design@coef).permute(0,3,1,2);pred=raw.clamp(0,1)
            yy=z[:,:,4:-4,4:-4];pp=pred[:,:,4:-4,4:-4];luma=z.new_tensor([.299,.587,.114]).view(1,3,1,1)
            rows.append({'split':split,'scene':stem,'RGB_MAE':float((yy-pp).abs().mean()),'luma_MAE':float(((yy-pp)*luma).sum(1).abs().mean()),'source':pr})
            if split=='validation12' and idx<4:
                sheet=Image.new('RGB',(256*3,278),'white');d=ImageDraw.Draw(sheet)
                for col,(label,v) in enumerate(zip(('INPUT resized256','FROZEN ENCODER LINEAR RGB','ABS ERROR x4'),(z,pred,(z-pred).abs()*4))):
                    im=Image.fromarray((v[0].clamp(0,1).permute(1,2,0).cpu().numpy()*255).round().astype(np.uint8));sheet.paste(im,(col*256,0));d.text((col*256+2,260),label,fill='black')
                sheet.save(out/f'{stem}.jpg',quality=95)
    summary={s:{k:float(np.mean([r[k] for r in rows if r['split']==s])) for k in ('RGB_MAE','luma_MAE')} for s in ('train_heldout32','validation12')}
    result={'time':now(),'checkpoint_sha256':sha(p),'source_sha256':sha(__file__),'training_performed':'linear readout only on32 train inputs; frozen V3 weights unchanged','fixed17_used':False,'protocol':'resize full images256, sample1024 inner locations per train image, FP32 encoder, FP64 SVD linear fit incl intercept, evaluate inner248 pixels; clipped RGB result','least_squares_rank':int(solve.rank),'singular_values':singular,'summary':summary,'activation_activity':activity,'rows':rows,'limitations':['Linear reconstruction success only rejects strong information-erasure claims at shallow features','Linear failure does not prove nonlinear information loss','Does not test art target learnability, locality or expert capacity']}
    (out/'result.json').write_text(json.dumps(result,indent=2));torch.save({'coef':coef.cpu(),'checkpoint_sha256':sha(p),'not_deployment':True},out/'linear_readout.pt');print(json.dumps({'rank':int(solve.rank),'summary':summary}),flush=True)
if __name__=='__main__':main()
