"""v9: public-domain Van Gogh references and v8-preserving continuation.

All additional computation is training only. Exported TinyStyleNet is unchanged.
"""
import argparse,hashlib,json,math,random,shutil,time
from pathlib import Path
import numpy as np
from PIL import Image,ImageOps
import torch
import torch.nn.functional as F
from tinystyle import TinyStyleNet,QCfg,macs_per_pixel
from train import ROOT,CropSet,image_list,camera_domain_augment
from train_art_styles_v4 import ArtFeatures,reference_bank,NAMES
from train_art_styles import gram
from art_material_v7 import PatchBank,shift_consistency
from art_structure_v8 import target,separated_loss,spatial_covariance,covariance_loss

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def aic_references(root,out,device,size):
    records=json.loads((root/'dataset_v2/manifests/aic_v9.json').read_text(encoding='utf-8'))
    refs=[]
    for rec in records:
        path=root/'dataset_v2'/rec['path']
        if sha(path)!=rec['sha256']:raise ValueError(f'AIC hash mismatch: {path}')
        if rec['role']!='train':continue
        if not rec['is_public_domain'] or 'oil' not in rec['medium_display'].lower():raise ValueError(rec['id'])
        im=ImageOps.fit(Image.open(path).convert('RGB'),(size,size),Image.Resampling.LANCZOS)
        x=torch.from_numpy(np.asarray(im).copy()).permute(2,0,1)[None].to(device).float()/255
        refs.append((x,1/4))
    if len(refs)!=4:raise ValueError('Expected four AIC training references')
    (out/'aic_references.json').write_text(json.dumps(records,indent=2,ensure_ascii=False),encoding='utf-8')
    return refs


class WeakPairs:
    def __init__(self,root,out):
        # Previously inspected figures 15/19 are development only, never fit.
        self.items=[];records=[]
        for i in (1,3,5,6,8,9,11,13,16,18):
            a=root/f'input_images/sample_{i:02}.jpg';b=root/f'processed_images/sample_{i:02}_vangogh_oil.png'
            x=ImageOps.exif_transpose(Image.open(a)).convert('RGB')
            t=Image.open(b).convert('RGB')
            if abs(x.width/x.height-t.width/t.height)>.01:raise ValueError('Aspect mismatch')
            w,h=x.size;scale=640/min(w,h)
            size=(round(w*scale),round(h*scale))
            self.items.append((x.resize(size,Image.Resampling.LANCZOS),t.resize(size,Image.Resampling.LANCZOS)))
            records.append(dict(id=i,input=str(a),target=str(b),input_sha256=sha(a),target_sha256=sha(b),
                repository='KShang29/van_gogh_oil_painting_transformation',commit='c5ff3e4f183fab46152d64708287bae048867c0b',
                role='weak training pair; not pixel-perfect; no new stylecam runtime code',
                provenance='upstream curated result; exact generator/settings unverified'))
        (out/'weak_pairs.json').write_text(json.dumps(records,indent=2,ensure_ascii=False),encoding='utf-8')

    def batch(self,n,size):
        xs=[];ts=[]
        for _ in range(n):
            a,b=random.choice(self.items);side=random.choice([320,448,576])
            w,h=a.size;left=random.randrange(w-side+1);top=random.randrange(h-side+1)
            box=(left,top,left+side,top+side)
            a=a.crop(box).resize((size,size),Image.Resampling.LANCZOS);b=b.crop(box).resize((size,size),Image.Resampling.LANCZOS)
            if random.random()<.5:a=ImageOps.mirror(a);b=ImageOps.mirror(b)
            xs.append(torch.from_numpy(np.asarray(a).copy()).permute(2,0,1));ts.append(torch.from_numpy(np.asarray(b).copy()).permute(2,0,1))
        return torch.stack(xs).cuda().float()/255,torch.stack(ts).cuda().float()/255


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True)
    p.add_argument('--init',default='runs/art_styles_c24_structure_v8_pilot900/student.pt')
    p.add_argument('--steps',type=int,default=900);p.add_argument('--batch',type=int,default=4)
    p.add_argument('--crop',type=int,default=256);p.add_argument('--lr',type=float,default=5e-5)
    p.add_argument('--seed',type=int,default=20261015);p.add_argument('--save_every',type=int,default=300)
    p.add_argument('--patch_weight',type=float,default=.08)
    p.add_argument('--preserve_weight',type=float,default=2.0)
    p.add_argument('--no_pairs',action='store_true');p.add_argument('--no_structure',action='store_true')
    args=p.parse_args();root=Path(ROOT);out=root/args.out;out.mkdir(parents=True,exist_ok=False)
    torch.set_num_threads(4);random.seed(args.seed);np.random.seed(args.seed);torch.manual_seed(args.seed)
    assert torch.cuda.is_available();torch.cuda.reset_peak_memory_stats()
    ck=torch.load(root/args.init,map_location='cpu',weights_only=False)
    assert ck['styles']==NAMES and ck['cfg']==dict(C=24,Fc=16,n_res=4,n_styles=3,norm='in',block='dw1')
    net=TinyStyleNet(**ck['cfg']).cuda();net.load_state_dict(ck['sd']);net.train()
    teacher=TinyStyleNet(**ck['cfg']).cuda().eval();teacher.load_state_dict(ck['sd']);teacher.requires_grad_(False)
    QCfg.enabled=QCfg.observe=False
    vgg=ArtFeatures().cuda().eval();refs=reference_bank(out,'cuda',args.crop,coarse_brush=True)
    aic=aic_references(root,out,'cuda',args.crop)
    targets=[];aic_bank=None
    with torch.no_grad():
        for si,row in enumerate(refs):
            features=[vgg(x) for x,w in row]
            gs=[sum(w*gram(fs[k]) for fs,(_,w) in zip(features,row)) for k in range(4)]
            cov=[sum(w*spatial_covariance(fs[0])[k] for fs,(_,w) in zip(features,row)) for k in range(5)]
            if si==0:
                art_features=[vgg(x) for x,w in aic]
                art_grams=[sum(w*gram(fs[k]) for fs,(_,w) in zip(art_features,aic)) for k in range(4)]
                art_cov=[sum(w*spatial_covariance(fs[0])[k] for fs,(_,w) in zip(art_features,aic)) for k in range(5)]
                gs=[.65*g+.35*a for g,a in zip(gs,art_grams)]
                cov=[.65*g+.35*a for g,a in zip(cov,art_cov)]
                aic_bank=PatchBank(art_features)
            targets.append((gs,cov))
    pairroot=root.parent.parent/'风格Skill研究_20261004/visual_study/vangogh'
    pairs=WeakPairs(pairroot,out) if not args.no_pairs else None
    train,held=image_list();assert not set(train)&set(held)
    dl=torch.utils.data.DataLoader(CropSet(train,args.crop),batch_size=args.batch,shuffle=True,num_workers=0,drop_last=True)
    config=dict(args=vars(args),cfg=ck['cfg'],init_sha256=sha(root/args.init),params=sum(x.numel() for x in net.parameters()),
        conv_MACs_VGA=macs_per_pixel(net.specs)[0]*640*480,graph_changed=False,quantization_validated=False,board_validated=False,
        aic_manifest_sha256=sha(root/'dataset_v2/manifests/aic_v9.json'),
        training_note='AIC Gram/covariance blend and patch loss for Van Gogh; v8 teacher preservation for other styles',
        train_files=[Path(f).name for f in train],development_files=[Path(f).name for f in held])
    (out/'config.json').write_text(json.dumps(config,indent=2),encoding='utf-8')
    snap=out/'source_snapshot';snap.mkdir()
    for n in ['train_art_styles_v9.py','art_structure_v8.py','art_material_v7.py','art_spatial_priors.py','train_art_styles_v4.py','train_art_styles.py','train.py','tinystyle.py']:
        shutil.copy2(root/'algo'/n,snap/n)
    opt=torch.optim.Adam(net.parameters(),lr=args.lr);start=time.monotonic();step=0;window=[]
    def save(name):
        tmp=out/(name+'.tmp')
        torch.save(dict(cfg=net.cfg,styles=NAMES,sd={k:v.detach().cpu() for k,v in net.state_dict().items()},qat=False,it=step,
            opt=opt.state_dict(),args=vars(args),seconds=time.monotonic()-start,needs_new_calibration=True,
            rng_python=random.getstate(),rng_numpy=np.random.get_state(),rng_torch=torch.get_rng_state(),rng_cuda=torch.cuda.get_rng_state_all()),tmp)
        tmp.replace(out/name)
    with (out/'train.jsonl').open('w',encoding='utf-8') as log:
        while step<args.steps:
            for xb in dl:
                si=step%3;paired=si==0 and pairs is not None and (step//3)%2==0
                if paired:x,t=pairs.batch(args.batch,args.crop)
                else:x=xb.cuda().float()/255;t=None
                xa=camera_domain_augment(x*255,.3)/255
                st=torch.full((len(x),),si,device='cuda',dtype=torch.long);y=net(xa,st)
                with torch.no_grad():fx=vgg(x);ft=vgg(t) if paired else None
                fy=vgg(y);gs,covs=targets[si]
                if paired:gs=[gram(f) for f in ft];covs=spatial_covariance(ft[0])
                ls=sum(F.mse_loss(gram(f),g.expand(len(x),-1,-1))/g.square().mean().clamp_min(1e-8) for f,g in zip(fy,gs))/4
                lc=F.mse_loss(fy[2],fx[2])/fx[2].square().mean().clamp_min(1e-6)
                tv=(y[:,:,1:]-y[:,:,:-1]).abs().mean()+(y[:,:,:,1:]-y[:,:,:,:-1]).abs().mean()
                direct=y.new_zeros(());gl=direct;tonal=direct;cov=direct;lt=direct;patch=direct;preserve=direct
                if si==0:
                    cov=covariance_loss(fy[0],covs)
                    patch=aic_bank.loss(fy[1])
                    loss=1.15*ls+.10*lc+.20*cov+args.patch_weight*patch+.005*tv
                    if paired:
                        # Weak alignment: match broad tone, not exact painted
                        # high-frequency pixels or hallucinated geometry.
                        direct=sum(F.l1_loss(F.avg_pool2d(y,k),F.avg_pool2d(t,k)) for k in (8,16,32))/3
                        loss=loss+1.2*direct
                else:
                    t=target(x,si);direct,gl,tonal=separated_loss(y,t)
                    if args.no_structure:
                        loss=8*F.l1_loss(y,t)+.04*ls+.05*lc+.01*tv
                    else:
                        loss=5*direct+5*gl+.04*ls+.05*lc+.008*tv
                        if si==2:loss=loss+1.5*tonal+10*(y-y.mean(1,keepdim=True)).square().mean()
                    with torch.no_grad():baseline=teacher(xa,st)
                    preserve=F.l1_loss(y,baseline)
                    loss=loss+args.preserve_weight*preserve
                if (step//3)%4==0:
                    lt=shift_consistency(net,xa,st,y,step)
                    loss=loss+.25*lt
                if not torch.isfinite(loss):raise RuntimeError(f'nonfinite {step}')
                lr=args.lr*(.3+.7*.5*(1+math.cos(math.pi*step/args.steps)))
                for g in opt.param_groups:g['lr']=lr
                opt.zero_grad(set_to_none=True);loss.backward();torch.nn.utils.clip_grad_norm_(net.parameters(),5,error_if_nonfinite=True);opt.step()
                step+=1;window.append(dict(style=NAMES[si],loss=float(loss),gram=float(ls),content=float(lc),direct=float(direct),gradient=float(gl),tonal=float(tonal),cov=float(cov),patch=float(patch),preserve=float(preserve),shift=float(lt),paired=int(paired)))
                if step%150==0 or step==args.steps:
                    r=dict(step=step,seconds=time.monotonic()-start,peak_mb=torch.cuda.max_memory_allocated()/2**20,
                        means={n:{k:float(np.mean([r[k] for r in window if r['style']==n])) for k in ['loss','gram','content','direct','gradient','tonal','cov','patch','preserve','shift']} for n in NAMES if any(r['style']==n for r in window)})
                    line=json.dumps(r);log.write(line+'\n');log.flush();print(line,flush=True);window=[]
                if step%args.save_every==0 or step==args.steps:save(f'step_{step:05}.pt')
                if step>=args.steps:break
    save('student.pt');print('SAVED',out,flush=True)

if __name__=='__main__':main()
