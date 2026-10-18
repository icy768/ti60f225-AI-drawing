"""P1b: paired capacity control, not an artistic candidate or automatic G1 pass."""
from pathlib import Path
import argparse
import datetime as dt
import hashlib
import json
import os
import random
import sys
import time

import numpy as np
import torch
from torch.nn import functional as F
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'diagnostics'))
from v3_access import V3, old, model_for_state

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def now(): return dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat()
def image_tensor(p): return torch.from_numpy(np.array(Image.open(p).convert('RGB'), copy=True)).permute(2,0,1).float()/255

class NonlinearMixer(torch.nn.Module):
    """Diagnostic residual1x1 branch; exact zero residual at initialization."""
    def __init__(self,base):
        super().__init__();self.base=base;c=base.conv.in_channels
        self.expand=torch.nn.Conv2d(c,32,1);self.relu=torch.nn.ReLU()
        self.project=torch.nn.Conv2d(32,c,1);self.add=torch.ao.nn.quantized.FloatFunctional()
        torch.nn.init.zeros_(self.project.weight);torch.nn.init.zeros_(self.project.bias)
    def forward(self,x):return self.add.add(self.base(x),self.project(self.relu(self.expand(x))))

def apply_nonlinear_mixer(model):
    assert not isinstance(model.experts[1].mix1,NonlinearMixer)
    model.experts[1].mix1=NonlinearMixer(model.experts[1].mix1)
    return model

def apply_architecture(model, dilation2=False):
    if dilation2:
        for mod in model.experts[1].s8.blocks.modules():
            if isinstance(mod,torch.nn.Conv2d) and mod.groups==mod.in_channels and mod.kernel_size!=(1,1):
                mod.dilation=tuple(2 if k>1 else 1 for k in mod.kernel_size)
                mod.padding=tuple(k//2*d for k,d in zip(mod.kernel_size,mod.dilation))
    return model

def sobel_target_loss(y,t):
    k=y.new_tensor([[[-1.,0.,1.],[-2.,0.,2.],[-1.,0.,1.]],
                    [[-1.,-2.,-1.],[0.,0.,0.],[1.,2.,1.]]])[:,None]/8
    lum=y.new_tensor([.299,.587,.114]).view(1,3,1,1)
    def edges(z):return F.conv2d(F.pad((z*lum).sum(1,keepdim=True),(1,1,1,1),mode='reflect'),k)
    return F.l1_loss(edges(y),edges(t))

def balanced_paired_pixel(y,t):
    """Paired-only reduction: restrain dominance of frequent target tones.

    Sixteen fixed luminance/chroma categories are derived from the SAME
    registered target; no artwork layout or photograph anchor enters here.
    """
    with torch.no_grad():
        lum=(t*t.new_tensor([.299,.587,.114]).view(1,3,1,1)).sum(1)
        tone=(lum*4).long().clamp(0,3);chroma=t.amax(1)-t.amin(1)
        hue=torch.where(chroma<.08,torch.full_like(tone,3),t.argmax(1))
        labels=tone*4+hue;freq=F.one_hot(labels,16).float().mean((1,2));class_w=(freq+1e-6).rsqrt().clamp_max(4.)
        weight=class_w.gather(1,labels.flatten(1)).reshape_as(lum);weight/=weight.mean((1,2),keepdim=True)
    return ((y-t).abs().mean(1)*weight).mean()

class Pairs:
    def __init__(self, split, limit):
        allowed = {Path(p.replace('\\','/')).stem for p in json.loads((V3/'data/splits.json').read_text())[split]}
        folder = V3/'data/claude_targets'
        files = [p for p in sorted((folder/'content'/split).glob('*.png')) if p.stem in allowed]
        # Spread selection across the complete split; never use fixed17.
        ids = np.linspace(0, len(files)-1, min(limit,len(files))).round().astype(int)
        self.rows = []
        for i in ids:
            p = files[i]; t = folder/'ukiyoe_p1'/split/p.name
            assert t.exists(); x,y = image_tensor(p),image_tensor(t); assert x.shape == y.shape
            self.rows.append((p.stem,x,y,{'input':str(p), 'target':str(t), 'input_sha256':sha(p),'target_sha256':sha(t)}))
    def batch(self, n, rng, full_frame=False):
        xs,ys=[],[]
        for _ in range(n):
            _,x,y,_ = self.rows[rng.randrange(len(self.rows))]; h,w=x.shape[-2:]
            if full_frame:
                x,y=[F.interpolate(z[None],size=(256,256),mode='bilinear',align_corners=False,antialias=True)[0] for z in (x,y)]
            else:
                top,left=rng.randrange(h-255),rng.randrange(w-255)
                x,y=x[:,top:top+256,left:left+256],y[:,top:top+256,left:left+256]
            if rng.random()<.5: x,y=x.flip(-1),y.flip(-1)
            xs.append(x);ys.append(y)
        return torch.stack(xs),torch.stack(ys)

@torch.no_grad()
def evaluate(model, base, sets, dest, device, resize256=False):
    model.eval(); base.eval(); dest.mkdir(parents=True,exist_ok=True); scores=[]
    for split,ds in sets:
        rows=ds.rows[:8] if split=='train' else ds.rows
        for page,offset in enumerate(range(0,len(rows),4)):
            subset=rows[offset:offset+4];sheet=Image.new('RGB',(4*256,len(subset)*218),'white');draw=ImageDraw.Draw(sheet)
            for ri,(stem,x,t,_) in enumerate(subset):
                if resize256:x,t=[F.interpolate(z[None],size=(256,256),mode='bilinear',align_corners=False,antialias=True)[0] for z in (x,t)]
                h,w=x.shape[-2:]; z=F.pad(x[None].to(device),(0,-w%8,0,-h%8),mode='replicate')
                y=model(z,1)[0,:,:h,:w].float().clamp(0,1).cpu();b=base(z,1)[0,:,:h,:w].float().clamp(0,1).cpu()
                scores.append({'split':split,'scene':stem,'target_L1':float((y-t).abs().mean()),'V3_target_L1':float((b-t).abs().mean())})
                for col,(label,v) in enumerate(zip(('INPUT','OLD UKIYOE_P1 TARGET','V3 FROZEN','PAIRED FIT STUDENT'),(x,t,b,y))):
                    im=Image.fromarray((v.permute(1,2,0).numpy()*255).round().astype(np.uint8))
                    im.save(dest/f'{split}_{stem}_{col}.png');im.thumbnail((256,192));sheet.paste(im,(col*256,ri*218));draw.text((col*256+2,ri*218+195),stem+' '+label,fill='black')
            sheet.save(dest/f'{split}_page{page+1}.jpg',quality=94)
    (dest/'metrics.json').write_text(json.dumps({'purpose':'paired fit diagnostic only; no art acceptance from L1','resize_full_frame_to256_square':resize256,'aspect_distorted_diagnostic_only':resize256,'rows':scores},indent=2))
    model.train()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--run',required=True);ap.add_argument('--steps',type=int,default=1500);ap.add_argument('--batch',type=int,default=8);ap.add_argument('--resume',action='store_true');ap.add_argument('--skip-scale',type=float,default=1.);ap.add_argument('--dilation2',action='store_true');ap.add_argument('--full-frame',action='store_true');ap.add_argument('--train-count',type=int,default=64);ap.add_argument('--plan-loss-control',action='store_true');ap.add_argument('--balanced-target-pixel',action='store_true');args=ap.parse_args()
    assert not args.balanced_target_pixel or (args.plan_loss_control and args.train_count==64 and not args.full_frame and not args.dilation2 and args.skip_scale==1.),'Compare one pixel-reduction intervention against original PLAN loss control'
    # Explicit opt-in diagnostic: change only encoder trainability, no graph expansion.
    shared_lr=float(os.environ.get('PAIRED_DIAGNOSTIC_SHARED_LR','0'))
    nonlinear_mixer=os.environ.get('PAIRED_DIAGNOSTIC_NONLINEAR_MIXER','0')=='1'
    assert not nonlinear_mixer or (args.plan_loss_control and not args.balanced_target_pixel and args.train_count==64 and not args.full_frame and not args.dilation2 and args.skip_scale==1. and not shared_lr),'One nonlinear-mixer intervention against PLAN loss control'
    assert shared_lr in (0.,1e-5)
    assert not shared_lr or (args.plan_loss_control and not args.balanced_target_pixel and args.train_count==64 and not args.full_frame and not args.dilation2 and args.skip_scale==1.)
    torch.set_num_threads(3);torch.manual_seed(20261097);np.random.seed(20261097);random.seed(20261097);rng=random.Random(20261097)
    assert torch.cuda.is_available();device='cuda';torch.backends.cudnn.benchmark=True
    out=ROOT/'experiments/paired_v5'/args.run;out.mkdir(parents=True,exist_ok=True);report=ROOT/'reports/paired_v5/P1b'/args.run;report.mkdir(parents=True,exist_ok=True)
    assert args.resume or not (out/'config.json').exists(),'New run name required'
    init=ROOT/'baseline/tristyle_v3_fp32.pt';state=torch.load(init,map_location='cpu',weights_only=False)['model'];model=model_for_state(state).to(device);model.load_state_dict(state)
    base=model_for_state(state).to(device).eval();base.load_state_dict(state)
    assert not (args.dilation2 and args.skip_scale!=1.),'One intervention at a time'
    apply_architecture(model,args.dilation2)
    if nonlinear_mixer:
        # A frozen comparison of raw network outputs at identical input must
        # prove that the new capacity does not initialize a style change.
        z=torch.zeros(1,3,64,64,device=device)
        with torch.no_grad():before=model(z,1).clone()
        apply_nonlinear_mixer(model).to(device)
        with torch.no_grad():assert torch.equal(before,model(z,1)),'Residual branch must initialize exactly to0'
    for p in base.parameters():p.requires_grad_(False)
    for n,p in model.named_parameters():p.requires_grad_(n.startswith('experts.1.') or bool(shared_lr and not n.startswith('experts.')))
    if args.skip_scale!=1.:
        with torch.no_grad():
            for stage,deep in ((model.experts[1].s4,88),(model.experts[1].s2,40),(model.experts[1].s1,24)):
                stage.fuse.conv.weight[:,deep:]*=args.skip_scale
    params=[p for p in model.parameters() if p.requires_grad]
    groups=[{'params':[p for n,p in model.named_parameters() if n.startswith('experts.1.')],'lr':2e-4}]
    if shared_lr:groups.append({'params':[p for n,p in model.named_parameters() if not n.startswith('experts.')],'lr':shared_lr})
    opt=torch.optim.Adam(groups,betas=(.9,.99));scaler=torch.amp.GradScaler('cuda');vgg=old.VGG().to(device).eval()
    assert 1<=args.train_count<=64
    train,val=Pairs('train',args.train_count),Pairs('validation',12)
    cfg={'run':args.run,'phase':'P1b','steps':args.steps,'batch':args.batch,'lr':2e-4,'AMP':True,'initial':str(init.relative_to(ROOT)),'initial_sha256':sha(init),'trainable':'experts.1 ALL including skip slices','skip_initial_scale':args.skip_scale,'content_route_constraint':False,'freeze_skip_routes':False,'suppress_skips_during_training':False,'losses':{'paired_L1':1.,'guide_perceptual_target_layers_1_2_3':.1},'photo_content':0,'semantic':0,'head_edge':0,'old_output_anchor':0,'adversarial':0,'critic_texture':False,'patch':0,'moment':0,'adv_patch_moment':0,'fixed17_used':False,'baseline_full64_validation92':'reports/paired_v5/P1b/p1b_uk_fit_01/full_split_baseline.json','parameter_count':sum(p.numel() for p in model.parameters()),'planned_INT8weight_INT32bias_bytes':sum(p.numel()*(4 if n.endswith('bias') else 1) for n,p in model.named_parameters()),'integer_exported':False,'sources':{}}
    cfg['expert1_s8_depthwise_dilation']=2 if args.dilation2 else 1
    cfg['expert1_nonlinear_mixer']=nonlinear_mixer
    if nonlinear_mixer:cfg['graph_reconstruction']='model_for_state(state), then apply_nonlinear_mixer(model), then load_state_dict; plain model_for_state cannot restore this graph'
    cfg['diagnostic_shared_lr']=shared_lr
    if shared_lr:cfg['trainable']='experts.1 at2e-4 + shared encoder at1e-5; other expert tensors frozen; DIAGNOSTIC ONLY, other-style outputs can change'
    cfg['training_view']='entire input and existing paired target resized together to256x256' if args.full_frame else 'random registered256 crop'
    cfg['context_control_only']=args.full_frame
    cfg['training_image_count']=len(train.rows)
    cfg['one_image_overfit_diagnostic']=args.train_count==1
    cfg['PLAN_section5_paired_loss_control']=args.plan_loss_control
    cfg['paired_pixel_reduction']='per-image16 target-derived tone/chroma categories, inverse-sqrt frequency capped4 then unit-mean weights' if args.balanced_target_pixel else 'uniform registered target RGB L1'
    cfg['balanced_target_pixel_diagnostic']=args.balanced_target_pixel
    if args.plan_loss_control:
        cfg['losses']={'paired_L1':1.5,'coarse_target_L1_pool8':1.5,'guide_perceptual_target_layers_1_2_3':.1,'Sobel_to_target':.5}
        cfg['diagnostic_limit']='P1b loss-recipe control only. Not P3, no temporal/equivariance in this short capacity test. Changes loss recipe jointly; do not attribute gains to any individual term.'
    cfg['full_frame_caveat']='Changes visible context and input scale together; cannot isolate a unique cause. Square aspect distortion is diagnostic only, not proposed deployment.' if args.full_frame else None
    cfg['dilation_note']='State tensor shapes do not encode dilation; reconstruct using apply_architecture(config), do not use model_for_state alone'
    for p in [Path(__file__),ROOT/'diagnostics/v3_access.py',ROOT/'baseline/source/claude_impl/model.py',ROOT/'baseline/source/claude_impl/train.py',ROOT/'CLAUDE_GUIDANCE.md',ROOT/'CLAUDE_SUPERVISION.md']:
        rel=p.relative_to(ROOT);dest=out/'source'/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(p.read_bytes());cfg['sources'][str(rel)]=sha(p)
    for p in (Path('D:/ClaudeTest/guidance/PLAN.md'),Path('D:/ClaudeTest/guidance/LATEST.md')):
        dest=out/'source/guidance'/p.name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(p.read_bytes());cfg['sources'][str(p)]=sha(p)
    (out/'config.json').write_text(json.dumps(cfg,indent=2));(out/'data_manifest.json').write_text(json.dumps({s:[{'stem':r[0],**r[3]} for r in ds.rows] for s,ds in [('train',train),('validation',val)]},indent=2))
    step=0
    if args.resume:
        ck=torch.load(out/'latest.pt',map_location=device,weights_only=False);model.load_state_dict(ck['model']);opt.load_state_dict(ck['opt']);scaler.load_state_dict(ck['scaler']);step=ck['step'];rng.setstate(ck['sample_rng']);torch.set_rng_state(ck['torch_rng'].cpu());torch.cuda.set_rng_state_all([x.cpu() for x in ck['cuda_rng']]);np.random.set_state(ck['numpy_rng']);random.setstate(ck['python_rng'])
    frozen={n:v.detach().cpu().clone() for n,v in model.state_dict().items() if not n.startswith('experts.1.') and not (shared_lr and not n.startswith('experts.'))}
    def save():
        for n,v in frozen.items(): assert torch.equal(v,model.state_dict()[n].cpu()),'Frozen tensor changed: '+n
        ck={'model':model.state_dict(),'opt':opt.state_dict(),'scaler':scaler.state_dict(),'step':step,'config':cfg,'sample_rng':rng.getstate(),'torch_rng':torch.get_rng_state(),'cuda_rng':torch.cuda.get_rng_state_all(),'numpy_rng':np.random.get_state(),'python_rng':random.getstate(),'frozen_tensors_equal':True}
        torch.save(ck,out/'latest.tmp');(out/'latest.tmp').replace(out/'latest.pt')
    started=time.time();log=(out/'metrics.jsonl').open('a',buffering=1);audit=(out/'gradient_audit.jsonl').open('a',buffering=1)
    for step in range(step+1,args.steps+1):
        if (out/'STOP').exists(): step-=1;break
        x,t=train.batch(args.batch,rng,full_frame=args.full_frame);x,t=x.to(device),t.to(device);model.train();opt.zero_grad(set_to_none=True)
        with torch.autocast('cuda',dtype=torch.float16):
            if shared_lr:features=model.encode(x)
            else:
                with torch.no_grad():features=model.encode(x)
            with torch.no_grad():ft=vgg(t)
            raw=model.experts[1](*features).float();y=raw.clamp(0,1)*.98+raw*.02;fy=vgg(y)
            pix=(balanced_paired_pixel(y,t) if args.balanced_target_pixel else F.l1_loss(y,t))*(1.5 if args.plan_loss_control else 1.);guide=sum(F.l1_loss(fy[j].float(),ft[j].float()) for j in (1,2,3))*.1
            coarse=F.l1_loss(F.avg_pool2d(y,8),F.avg_pool2d(t,8))*1.5 if args.plan_loss_control else y.new_zeros(())
            sobel=sobel_target_loss(y,t)*.5 if args.plan_loss_control else y.new_zeros(())
            loss=pix+guide+coarse+sobel
        assert torch.isfinite(loss)
        if step in (1,100,500,1000):
            gs=[]
            for name,l in [('paired_L1',pix),('target_perceptual',guide)]+([('coarse_target',coarse),('Sobel_target',sobel)] if args.plan_loss_control else []):
                scale=scaler.get_scale();g=torch.autograd.grad(l*scale,params,retain_graph=True,allow_unused=True);gs.append([z.float()/scale for z in g if z is not None]);audit.write(json.dumps({'step':step,'term':name,'weighted_loss':float(l.detach()),'grad_l2':float(sum(z.square().sum() for z in gs[-1]).sqrt()),'audit_scale':scale,'AMP_underflow_avoided':True})+'\n')
        scaler.scale(loss).backward();scaler.unscale_(opt);gn=torch.nn.utils.clip_grad_norm_(params,3.,error_if_nonfinite=True);scaler.step(opt);scaler.update()
        if step==1 or step%25==0:
            row={'time':now(),'step':step,'loss':float(loss.detach()),'paired_L1':float(pix.detach()),'guide_perceptual_weighted':float(guide.detach()),'coarse_target_weighted':float(coarse.detach()),'Sobel_target_weighted':float(sobel.detach()),'grad_norm':float(gn),'seconds':time.time()-started,'pid':os.getpid()};log.write(json.dumps(row)+'\n');print('P1B',json.dumps(row),flush=True)
        if step%100==0:save()
        if step%500==0 or step==args.steps:
            save();torch.save({'model':model.state_dict(),'config':cfg,'step':step},out/f'step_{step:06d}.pt');evaluate(model,base,[('train',train),('validation',val)],report/f'{step:06d}',device)
            if args.full_frame:evaluate(model,base,[('train',train),('validation',val)],report/f'{step:06d}'/'full_frame256_diagnostic',device,resize256=True)
        (ROOT/'STATE.json').write_text(json.dumps({'time':now(),'phase':'P1b paired ukiyoe capacity control','pid':os.getpid(),'run':str(out.relative_to(ROOT)),'step':step,'gate':'G1_NOT_PASSED','promoted':False,'next':'Inspect P1 targets and P1b actual target/student images; read supervision before G1'},indent=2)) if step==1 or step%100==0 else None
    save();(out/'finished.json').write_text(json.dumps({'time':now(),'step':step,'completed_plan':step==args.steps,'promoted':False,'frozen_tensors_equal':True},indent=2));print('P1B_FINISHED_VISUAL_REVIEW_REQUIRED',flush=True)

if __name__=='__main__':main()
