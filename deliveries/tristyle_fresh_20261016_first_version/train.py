"""Three stages, deterministic split, actual perceptual/local spatial supervision.
Run via runner.py to obtain deadline-aware checkpoints and final exports.
"""
import os,time,json,random,argparse,pathlib,math,copy
import numpy as np,torch
from torch import nn
from torch.nn import functional as F
from torch.utils.data import DataLoader
from model import TriStyle,STYLES
from data import ROOT,ContentDataset,image_tensor,reference_crop
from losses import Perceptual,PatchDiscriminator,feature_norm,moment_loss,patch_loss,style_spatial,edge_content,local_covariance_loss,teacher_texture
from teachers import CycleTeacher
from adain_teacher import AdaINTeacher
TRAIN_STATE_PROVIDER=None
RUN_NAME='unassigned'

def seed_all(seed):
    random.seed(seed);np.random.seed(seed);torch.manual_seed(seed);torch.cuda.manual_seed_all(seed)
def checkpoint(path,model,opt,step,stage,config,extra=None):
    path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix('.tmp')
    torch.save({'model':model.state_dict(),'optimizer':opt.state_dict(),'step':step,'stage':stage,'config':config,'rng_torch':torch.get_rng_state(),'rng_cuda':torch.cuda.get_rng_state_all(),'rng_python':random.getstate(),'rng_numpy':np.random.get_state(),'training_state':TRAIN_STATE_PROVIDER() if TRAIN_STATE_PROVIDER else {},'extra':extra or {}},tmp);tmp.replace(path)
def evaluate(model,step):
    from PIL import Image
    from prepare_data import save_gallery
    dst=ROOT/f'reports/progress/{RUN_NAME}/{step:06d}';dst.mkdir(parents=True,exist_ok=True)
    old=model.training;model.eval();paths=[];labels=[]
    with torch.inference_mode():
        for p in sorted((ROOT/'data/test').glob('*.png')):
            im=Image.open(p).convert('RGB');im.thumbnail((384,288));w,h=im.size;x=image_tensor(p,(max(8,w//8*8),max(8,h//8*8))).unsqueeze(0).cuda()
            paths.append(p);labels.append(p.stem+' input')
            for s in range(3):
                y=model(x,s).clamp(0,1);a=(y[0].cpu().permute(1,2,0).numpy()*255).round().astype(np.uint8)
                q=dst/f'{p.stem}_{STYLES[s]}.png';Image.fromarray(a).save(q);paths.append(q);labels.append(STYLES[s])
    save_gallery(paths,dst/'comparison.jpg',labels,columns=4)
    model.train(old)
    return str(dst.relative_to(ROOT))

def main():
    global TRAIN_STATE_PROVIDER,RUN_NAME
    ap=argparse.ArgumentParser();ap.add_argument('--steps',type=int,default=30000);ap.add_argument('--size',type=int,default=256);ap.add_argument('--batch',type=int,default=3);ap.add_argument('--warmup',type=int,default=400);ap.add_argument('--specialize',type=int,default=9000);ap.add_argument('--deadline',default='2026-10-17T08:45:00+08:00');ap.add_argument('--resume',default='');ap.add_argument('--init-from',default='');ap.add_argument('--eval-every',type=int,default=300);ap.add_argument('--seed',type=int,default=20261016);ap.add_argument('--run',default='run01');args=ap.parse_args()
    from datetime import datetime
    deadline=datetime.fromisoformat(args.deadline).timestamp()
    RUN_NAME=args.run
    cfg=vars(args);seed_all(args.seed);torch.set_num_threads(4);torch.backends.cudnn.benchmark=True
    out=ROOT/'runs'/args.run;out.mkdir(parents=True,exist_ok=True);(out/'config.json').write_text(json.dumps(cfg,indent=2))
    import hashlib,platform,shutil
    code=out/'source';code.mkdir(exist_ok=True)
    for p in ROOT.glob('*.py'):shutil.copy2(p,code/p.name)
    (out/'provenance.json').write_text(json.dumps({'source_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in code.glob('*.py')},'python':platform.python_version(),'torch':torch.__version__,'cuda':torch.version.cuda,'device':torch.cuda.get_device_name(),'seed':args.seed,'determinism':'cudnn benchmark enabled; bit exact training replay not guaranteed; source/config/data/RNG recorded'},indent=2))
    dataset=ContentDataset(size=args.size);loader=DataLoader(dataset,batch_size=args.batch,shuffle=True,num_workers=0,pin_memory=True,drop_last=True)
    iterator=iter(loader);model=TriStyle().cuda().train()
    opt=torch.optim.Adam(model.parameters(),lr=8e-4,betas=(.5,.99));step0=0
    if args.init_from:
        init=torch.load(args.init_from,map_location='cpu',weights_only=False);missing=model.load_state_dict(init['model'],strict=False);print('NEW PROJECT ITERATION INIT',missing,flush=True)
    # Only trusted self-produced checkpoint supports optimizer/RNG restoration.
    if args.resume:
        sd=torch.load(args.resume,map_location='cpu',weights_only=False);model.load_state_dict(sd['model']);opt.load_state_dict(sd['optimizer']);step0=sd['step']
        if 'rng_torch' in sd:
            torch.set_rng_state(sd['rng_torch']);torch.cuda.set_rng_state_all(sd['rng_cuda']);random.setstate(sd['rng_python']);np.random.set_state(sd['rng_numpy'])
    percept=Perceptual(ROOT/'teachers/weights/vgg16.pth').cuda().eval()
    teachers=[CycleTeacher(ROOT/'teachers/weights/cycle_vangogh.pth'),CycleTeacher(ROOT/'teachers/weights/cycle_ukiyoe.pth')]
    adain=AdaINTeacher(ROOT).cuda().eval()
    discs=nn.ModuleList([PatchDiscriminator() for _ in range(3)]).cuda().train()
    dopts=[torch.optim.Adam(d.parameters(),lr=1e-4,betas=(.5,.99)) for d in discs]
    scaler=torch.amp.GradScaler('cuda');started=time.time();best=[float('inf')]*3;ema=[None]*3
    if args.resume and sd.get('training_state'):
        ts=sd['training_state'];discs.load_state_dict(ts['discriminators'])
        for o,st in zip(dopts,ts['dopts']):o.load_state_dict(st)
        scaler.load_state_dict(ts['scaler'])
    TRAIN_STATE_PROVIDER=lambda:{'discriminators':discs.state_dict(),'dopts':[o.state_dict() for o in dopts],'scaler':scaler.state_dict()}
    # Validation proxy is separate from artistic acceptance and never includes fixed test images.
    valid=ContentDataset('validation',size=args.size)
    log=(out/'metrics.jsonl').open('a',encoding='utf-8',buffering=1)
    stop_reason='steps';last_stage='';step=step0
    try:
        for step in range(step0+1,args.steps+1):
            if time.time()>deadline:stop_reason='deadline reserve for export';break
            if (out/'STOP').exists():stop_reason='STOP request';break
            try:x=next(iterator).cuda(non_blocking=True)
            except StopIteration:dataset.refresh();valid.refresh();iterator=iter(loader);x=next(iterator).cuda(non_blocking=True)
            s=(step-1)%3
            stage='skeleton' if step<=args.warmup else 'specialize' if step<=args.warmup+args.specialize else 'joint'
            if stage!=last_stage:
                for p in list(model.stem.parameters())+list(model.down2.parameters())+list(model.down4.parameters())+list(model.down8.parameters()):p.requires_grad_(stage!='specialize')
                print('STAGE',stage,'STEP',step,flush=True);last_stage=stage
            lr=8e-4 if stage=='skeleton' else 4e-4 if stage=='specialize' else 1.5e-4
            for g in opt.param_groups:g['lr']=lr
            opt.zero_grad(set_to_none=True)
            with torch.autocast('cuda',dtype=torch.float16):
                y=model(x,s)
                if stage=='skeleton':
                    loss=F.l1_loss(y,x)+.3*edge_content(y,x);terms={'reconstruction':loss}
                else:
                    ref=reference_crop(STYLES[s],args.size).unsqueeze(0).cuda()
                    with torch.no_grad():
                        xf=percept(x);rf=percept(ref)
                        teacher=teachers[s](x).clamp(0,1) if s<2 else None
                        tf=percept(teacher) if teacher is not None else None
                        anchors=['data/references/vangogh/starry_night.jpg','data/references/ukiyoe/36492.jpg','data/references/ink/45683.jpg']
                        anchor=image_tensor(ROOT/anchors[s],(384,384)).unsqueeze(0).cuda()
                        alternate=adain(x,anchor,alpha=1.)
                        af=percept(alternate) if alternate is not None else None
                    yf=percept(y)
                    content=sum(F.mse_loss(feature_norm(yf[i]),feature_norm(xf[i])) for i in [2,3])
                    patch=sum(patch_loss(yf[i],rf[i]) for i in [0,1])
                    moments=sum(moment_loss(a,b) for a,b in zip(yf,rf))
                    local_style=sum(local_covariance_loss(yf[i],rf[i]) for i in [0,1,2])
                    spatial=style_spatial(y,ref,s,x)
                    coarse=edge_content(y,x)
                    distill=y.new_zeros(())
                    if tf is not None:
                        # Teacher contributes local/perceptual structure, not dominant pixel regression.
                        distill=sum(F.l1_loss(yf[i],tf[i]) for i in [0,1])*.2+F.l1_loss(F.avg_pool2d(y,16),F.avg_pool2d(teacher,16))*.4
                    if af is not None:
                        # Downweight transferred areas whose semantic features disagree with content.
                        with torch.no_grad():confidence=torch.exp(-(feature_norm(af[3])-feature_norm(xf[3])).square().mean(1,keepdim=True))
                        distill=distill+sum(((yf[i]-af[i]).abs()*F.interpolate(confidence,size=yf[i].shape[-2:],mode='bilinear',align_corners=False)).mean() for i in [0,1,2])
                        distill=distill+teacher_texture(y,alternate)*2.
                    for p in discs[s].parameters():p.requires_grad_(False)
                    adversarial=F.mse_loss(discs[s](y),torch.ones_like(discs[s](y)))
                    # Synthetic motion equivariance is a training regularizer, not a real-video metric.
                    temporal=y.new_zeros(())
                    if step%4==0:
                        shifted=torch.roll(x,shifts=(0,4),dims=(2,3));ys=model(shifted,s)
                        temporal=F.l1_loss(ys[:,:,:,16:-16],torch.roll(y,shifts=(0,4),dims=(2,3))[:,:,:,16:-16].detach())
                    if step%12==0:
                        pairfiles=list((ROOT/'data/video/train_pairs').glob('*.npz'))
                        if pairfiles:
                            pair=np.load(random.choice(pairfiles));a=torch.from_numpy(pair['a'].copy()).permute(2,0,1).unsqueeze(0).cuda().float()/255.;b=torch.from_numpy(pair['b'].copy()).permute(2,0,1).unsqueeze(0).cuda().float()/255.
                            flow=torch.from_numpy(pair['backward'].copy()).cuda().float();vh,vw=flow.shape[:2];gy,gx=torch.meshgrid(torch.arange(vh,device='cuda'),torch.arange(vw,device='cuda'),indexing='ij')
                            grid=torch.stack([(gx+flow[...,0])*2/(vw-1)-1,(gy+flow[...,1])*2/(vh-1)-1],-1).unsqueeze(0)
                            with torch.no_grad():
                                ya=model(a,s);wa=F.grid_sample(a,grid,align_corners=True);wya=F.grid_sample(ya.float(),grid,align_corners=True)
                                mask=((wa-b).abs().mean(1,keepdim=True)<.12).float()*((grid.abs()<.98).all(-1).unsqueeze(1))
                            yb=model(b,s);temporal=temporal+((yb-wya.detach()).abs()*mask).sum()/(mask.sum()*3+1)
                    terms={'content':content,'patch':patch,'local_style':local_style,'moments':moments,'spatial':spatial,'coarse':coarse,'distill':distill,'adversarial':adversarial,'temporal':temporal}
                    loss=content*.35+patch*.4+local_style*8.+moments*.12+spatial*1.5+coarse*.10+distill*4.+adversarial*.5+temporal*.2
            if not torch.isfinite(loss):raise FloatingPointError('nonfinite generator loss')
            scaler.scale(loss).backward();scaler.unscale_(opt);nn.utils.clip_grad_norm_(model.parameters(),5.);scaler.step(opt);scaler.update()
            if stage!='skeleton':
                for p in discs[s].parameters():p.requires_grad_(True)
                dopts[s].zero_grad(set_to_none=True)
                # FP32 discriminator update avoids mixed precision scaler coupling.
                real=discs[s](ref.float());fake=discs[s](y.detach().float())
                dl=.5*((real-1).square().mean()+fake.square().mean());dl.backward();nn.utils.clip_grad_norm_(discs[s].parameters(),5.);dopts[s].step()
            val=float(loss.detach());ema[s]=val if ema[s] is None else .98*ema[s]+.02*val
            if step%10==0:
                row={'step':step,'stage':stage,'style':STYLES[s],'loss':val,'elapsed_sec':time.time()-started,'terms':{k:float(v.detach()) for k,v in terms.items()}}
                log.write(json.dumps(row)+'\n')
            if step%50==0:print('STEP',step,stage,'LOSS',round(val,4),'SEC/STEP',round((time.time()-started)/(step-step0),3),flush=True)
            if step%100==0:checkpoint(out/'latest.pt',model,opt,step,stage,cfg,{'best_proxy':best,'ema':ema})
            if step%args.eval_every==0:
                checkpoint(out/f'step_{step:06d}.pt',model,opt,step,stage,cfg)
                gallery=evaluate(model,step);print('GALLERY',gallery,flush=True)
                if stage!='skeleton':
                    model.eval()
                    with torch.inference_mode():
                        vx=torch.stack([valid[i] for i in range(min(4,len(valid)))]).cuda();vxf=percept(vx)
                        for vs in range(3):
                            vy=model(vx,vs);vyf=percept(vy);vr=reference_crop(STYLES[vs],args.size).unsqueeze(0).cuda();vrf=percept(vr)
                            score=float(sum(F.mse_loss(feature_norm(vyf[i]),feature_norm(vxf[i])) for i in [2,3])+sum(moment_loss(a,b) for a,b in zip(vyf,vrf))*.04)
                            if score<best[vs]:best[vs]=score;checkpoint(out/f'best_proxy_{STYLES[vs]}.pt',model,opt,step,stage,cfg,{'proxy_score':score,'not_artistic_acceptance':True})
                    model.train()
                (out/'status.json').write_text(json.dumps({'step':step,'stage':stage,'gallery':gallery,'time_local':time.strftime('%Y-%m-%d %H:%M:%S'),'best_proxy':best},indent=2))
    finally:
        checkpoint(out/'latest.pt',model,opt,step,last_stage,cfg,{'stop_reason':stop_reason,'best_proxy':best})
        evaluate(model,step)
        (out/'finished.json').write_text(json.dumps({'step':step,'stage':last_stage,'reason':stop_reason,'elapsed_sec':time.time()-started},indent=2));log.close()
    print('TRAINING FINISHED',stop_reason,step,flush=True)
if __name__=='__main__':main()
