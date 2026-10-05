"""Controlled v6 continuation and material-supervision candidate; fixed graph."""
import argparse,hashlib,json,math,random,shutil,time
from pathlib import Path
import numpy as np
import torch
import torch.nn.functional as F
from tinystyle import QCfg,TinyStyleNet,param_count,macs_per_pixel
from train import ROOT,CropSet,camera_domain_augment,image_list
from train_art_styles import gram
from train_art_styles_v4 import ArtFeatures,reference_bank,NAMES,blur,edge
from art_spatial_priors import target as old_target,palette_distance
from art_material_v7 import PatchBank,material_target,shift_consistency,woodblock_palette_loss


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--init',default='runs/art_styles_c24_graphic_v6/student.pt')
    ap.add_argument('--out',required=True)
    ap.add_argument('--variant',choices=['control','material','material_strong','material_graphic'],default='material')
    ap.add_argument('--independent_style',choices=NAMES,default=None)
    ap.add_argument('--steps',type=int,default=1200)
    ap.add_argument('--batch',type=int,default=4)
    ap.add_argument('--crop',type=int,default=256)
    ap.add_argument('--lr',type=float,default=1.5e-4)
    ap.add_argument('--seed',type=int,default=20261005)
    ap.add_argument('--save_every',type=int,default=300)
    ap.add_argument('--patch_weight',type=float,default=.6)
    ap.add_argument('--temporal_weight',type=float,default=.15)
    args=ap.parse_args()
    root=Path(ROOT);out=root/args.out
    out.mkdir(parents=True,exist_ok=False)
    torch.set_num_threads(4)
    random.seed(args.seed);np.random.seed(args.seed);torch.manual_seed(args.seed)
    if not torch.cuda.is_available():raise RuntimeError('CUDA unavailable')
    torch.cuda.reset_peak_memory_stats()
    ck=torch.load(root/args.init,map_location='cpu',weights_only=False)
    assert ck['cfg']==dict(C=24,Fc=16,n_res=4,n_styles=3,norm='in',block='dw1')
    assert ck['styles']==NAMES
    selected=NAMES.index(args.independent_style) if args.independent_style else None
    names=[args.independent_style] if args.independent_style else NAMES
    cfg=dict(ck['cfg'])
    if selected is not None:cfg['n_styles']=1
    init_sd={k:(v[selected:selected+1] if selected is not None and
                 k.endswith(('.norm.gamma','.norm.beta')) else v) for k,v in ck['sd'].items()}
    net=TinyStyleNet(**cfg).cuda();net.load_state_dict(init_sd);net.train()
    teacher=None
    if args.variant in ('material_strong','material_graphic'):
        teacher=TinyStyleNet(**cfg).cuda().eval()
        teacher.load_state_dict(init_sd)
        teacher.requires_grad_(False)
    QCfg.enabled=QCfg.observe=False
    vgg=ArtFeatures().cuda().eval()
    refs=reference_bank(out,'cuda',args.crop,coarse_brush=True)
    targets=[]
    with torch.no_grad():
        for local in refs:
            fs=[vgg(x) for x,w in local]
            gs=[sum(w*f[i] for f,(_,w) in zip([[gram(a) for a in row] for row in fs],local)) for i in range(4)]
            color=sum(w*x.mean((2,3)) for x,w in local)
            targets.append((gs,color,PatchBank(fs)))
    train,held=image_list();assert not set(train)&set(held)
    dl=torch.utils.data.DataLoader(CropSet(train,args.crop),batch_size=args.batch,shuffle=True,drop_last=True,num_workers=0)
    opt=torch.optim.Adam(net.parameters(),lr=args.lr)
    snap=out/'source_snapshot';snap.mkdir()
    for name in ['train_art_styles_v7.py','art_material_v7.py','train_art_styles_v4.py','art_spatial_priors.py','tinystyle.py','train.py','train_art_styles.py']:
        shutil.copy2(Path(__file__).parent/name,snap/name)
    config=dict(args=vars(args),cfg=net.cfg,init_sha256=sha(root/args.init),
                train_files=[Path(p).name for p in train],development_files=[Path(p).name for p in held],
                graph_changed=False,params=sum(p.numel() for p in net.parameters()),
                convolution_MACs_VGA=macs_per_pixel(net.specs)[0]*640*480,
                quantization_validated=False,board_validated=False)
    (out/'config.json').write_text(json.dumps(config,indent=2),encoding='utf-8')
    def save(name,step):
        path=out/name;temp=path.with_suffix('.tmp')
        torch.save(dict(cfg=net.cfg,styles=names,sd={k:v.detach().cpu() for k,v in net.state_dict().items()},
                    opt=opt.state_dict(),qat=False,it=step,args=vars(args),seconds=time.monotonic()-start,
                    rng_python=random.getstate(),rng_numpy=np.random.get_state(),rng_torch=torch.get_rng_state(),rng_cuda=torch.cuda.get_rng_state_all(),
                    style_training='v7 '+args.variant+'; training-only losses, no new runtime operators',
                    init_sha256=config['init_sha256'],needs_new_calibration=True),temp)
        temp.replace(path)
    step=0;start=time.monotonic();window=[]
    with (out/'train.jsonl').open('w',encoding='utf-8') as log:
        while step<args.steps:
            for xb in dl:
                si=selected if selected is not None else step%3
                x=xb.cuda().float()/255
                xa=camera_domain_augment(x*255,.30)/255
                st=torch.full((len(x),),0 if selected is not None else si,device='cuda',dtype=torch.long)
                y=net(xa,st)
                with torch.no_grad(): fx=vgg(x)
                fy=vgg(y);gs,color,bank=targets[si]
                ls=sum(F.mse_loss(gram(f),g.expand(len(x),-1,-1))/g.square().mean().clamp_min(1e-8) for f,g in zip(fy,gs))/4
                lc=F.mse_loss(fy[2],fx[2])/fx[2].square().mean().clamp_min(1e-6)
                palette=F.mse_loss(y.mean((2,3)),color.expand(len(x),-1))
                chroma=(y-y.mean(1,keepdim=True)).square().mean()
                tv=(y[:,:,1:]-y[:,:,:-1]).abs().mean()+(y[:,:,:,1:]-y[:,:,:,:-1]).abs().mean()
                lp=y.new_zeros(());lt=y.new_zeros(());direct=y.new_zeros(())
                if args.variant=='control':
                    if si==0:loss=1.4*ls+.11*lc+.6*palette+.015*tv
                    else:
                        with torch.no_grad(): t=old_target(x,si)
                        direct=F.l1_loss(y,t);ll=F.l1_loss(edge(y),edge(t))
                        flat=(1-edge(blur(x))/.04).clamp(0,1).detach()
                        grain=((y-blur(y)).abs()*flat).mean()
                        loss=.10*ls+.07*lc+3*direct+3*ll+1.2*grain+.02*tv
                        loss=loss+(.5*palette_distance(y,x) if si==1 else 20*chroma)
                else:
                    lp=bank.loss(fy[1])
                    if si==0:
                        if args.variant in ('material_strong','material_graphic'):
                            with torch.no_grad(): baseline=teacher(xa,st)
                            direct=F.l1_loss(y,baseline)
                            loss=2*direct+.45*ls+.10*lc+.35*lp+.006*tv
                        else:
                            loss=1.2*ls+.16*lc+args.patch_weight*lp+.10*palette+.010*tv
                    else:
                        t=material_target(x,si)
                        if args.variant in ('material_strong','material_graphic') and si==2:
                            t=.65*old_target(x,si)+.35*t
                        direct=F.l1_loss(y,t);ll=F.l1_loss(edge(y),edge(t))
                        flat=(1-edge(blur(t))/.035).clamp(0,1).detach()
                        grain=((y-blur(y)).abs()*flat).mean()
                        if args.variant in ('material_strong','material_graphic'):
                            edge_weight=4 if args.variant=='material_graphic' and si==1 else 2
                            loss=.05*ls+.05*lc+8*direct+edge_weight*ll+.6*grain+.01*tv
                            if args.variant=='material_graphic' and si==1:
                                loss=loss+6*woodblock_palette_loss(y,x)
                            if si==2:loss=loss+15*chroma
                        else:
                            loss=.18*ls+.10*lc+3*direct+1.5*ll+1.5*grain+.08*lp+.015*tv
                            if si==2:loss=loss+15*chroma
                    if step%4==0 and args.temporal_weight:
                        lt=shift_consistency(net,xa,st,y,step)
                        loss=loss+args.temporal_weight*lt
                if not torch.isfinite(loss):raise RuntimeError(f'nonfinite step {step}')
                lr=args.lr*(.25+.75*.5*(1+math.cos(math.pi*step/args.steps)))
                for group in opt.param_groups:group['lr']=lr
                opt.zero_grad(set_to_none=True);loss.backward()
                gn=torch.nn.utils.clip_grad_norm_(net.parameters(),5,error_if_nonfinite=True);opt.step()
                step+=1
                window.append(dict(style=NAMES[si],loss=float(loss),gram=float(ls),content=float(lc),patch=float(lp),direct=float(direct),shift=float(lt),gradnorm=float(gn)))
                if step%150==0 or step==args.steps:
                    record=dict(step=step,seconds=time.monotonic()-start,lr=lr,peak_cuda_mb=torch.cuda.max_memory_allocated()/2**20,
                        losses={n:{k:float(np.mean([r[k] for r in window if r['style']==n])) for k in ['loss','gram','content','patch','direct','shift','gradnorm']}
                                for n in names if any(r['style']==n for r in window)})
                    line=json.dumps(record);log.write(line+'\n');log.flush();print(line,flush=True);window=[]
                if step%args.save_every==0 or step==args.steps:save(f'step_{step:05d}.pt',step)
                if step>=args.steps:break
    save('student.pt',step)
    print('SAVED',out/'student.pt',flush=True)


if __name__=='__main__':main()
