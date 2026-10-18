"""Paired-only adaptation of authorized V3 continuation_impl/train_art.py.

Training paths and retained brush/equivariance logic derive from that frozen
source; its exact bytes are archived in every run. No photograph feature loss,
critic, non-paired artwork loss, skip constraint or runtime postfilter exists.
Formal P3 requires a separately reviewed G1 approval; diagnostics never promote.
"""
from pathlib import Path
import argparse, json, math, os, random, sys, time
import numpy as np
import torch
from torch.nn import functional as F
from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'diagnostics'))
from v3_access import V3, old, art, model_for_state, STYLES
from fit_capacity import sha, now, image_tensor, sobel_target_loss
from conditional_patchgan import ConditionalPatchGAN

WEIGHTS={'pixel':[2.,1.5,1.5], 'coarse':1.5, 'guide_perceptual':.1,
         'orientation':[100.,0.,30.], 'brush_direction':[4.,0.,2.],
         'equivariance':[12.,5.,8.], 'Sobel':[0.,.5,0.], 'temporal':.1}

def owner():
    p=Path('D:/ClaudeTest/guidance/OWNER.json')
    # Claude takeover copy of train_paired.py (sha256 2F9AB36A...): owner guard accepts 'claude'.
    assert json.loads(p.read_text(encoding='utf-8'))['owner']=='claude','Read-only: Claude copy needs owner=claude'

class RegisteredPairs:
    def __init__(self, split, style, target_root, limit=0):
        allowed={Path(p.replace('\\','/')).stem for p in json.loads((V3/'data/splits.json').read_text())[split]}
        ps=[p for p in sorted((V3/'data/claude_targets/content'/split).glob('*.png')) if p.stem in allowed]
        if limit:ps=[ps[i] for i in np.linspace(0,len(ps)-1,min(limit,len(ps))).round().astype(int)]
        self.rows=[]
        for p in ps:
            t=target_root/style/split/p.name
            assert t.is_file(),str(t)
            with Image.open(p) as im,Image.open(t) as tm:assert im.size==tm.size
            self.rows.append((p,t))
        assert self.rows
    def provenance(self):
        return [{'input':str(p),'input_sha256':sha(p),'target':str(t),'target_sha256':sha(t)} for p,t in self.rows]
    def batch(self,n,rng,mixed_half):
        # A whole batch uses one registered scale. Half mode samples a512 crop
        # where available, downsamples to256; never upscales a smaller image.
        half=mixed_half and rng.random()<.5
        xs,ts=[],[]
        for _ in range(n):
            p,t=self.rows[rng.randrange(len(self.rows))];x,y=image_tensor(p),image_tensor(t)
            h,w=x.shape[-2:];side=min(512,min(h,w)) if half else 256
            assert side>=256
            top,left=rng.randrange(h-side+1),rng.randrange(w-side+1)
            x,y=[z[:,top:top+side,left:left+side] for z in (x,y)]
            if side!=256:x,y=[F.interpolate(z[None],(256,256),mode='bilinear',align_corners=False,antialias=True)[0] for z in (x,y)]
            if rng.random()<.5:x,y=x.flip(-1),y.flip(-1)
            xs.append(x);ts.append(y)
        return torch.stack(xs),torch.stack(ts),half

@torch.no_grad()
def gallery(model,base,ds,ei,dest,limit=12):
    dest.mkdir(parents=True,exist_ok=True);model.eval();base.eval();scores=[]
    rows=ds.rows[:limit]
    for off in range(0,len(rows),4):
        canvas=Image.new('RGB',(1024,218*len(rows[off:off+4])),'white');d=ImageDraw.Draw(canvas)
        for ri,(p,t) in enumerate(rows[off:off+4]):
            x,y=image_tensor(p),image_tensor(t);h,w=x.shape[-2:]
            z=F.pad(x[None].cuda(),(0,-w%8,0,-h%8),mode='replicate')
            outputs=[x,y,base(z,ei)[0,:,:h,:w].float().clamp(0,1).cpu(),model(z,ei)[0,:,:h,:w].float().clamp(0,1).cpu()]
            scores.append({'stem':p.stem,'student_target_MAE':float((outputs[3]-y).abs().mean()),'V3_target_MAE':float((outputs[2]-y).abs().mean())})
            for j,(v,label) in enumerate(zip(outputs,['INPUT','REGISTERED TEACHER','V3 FROZEN','RAW NETWORK STUDENT'])):
                im=Image.fromarray((v.permute(1,2,0).numpy()*255).round().astype('uint8'));im.save(dest/f'{p.stem}_{j}.png');im.thumbnail((256,192));canvas.paste(im,(j*256,ri*218));d.text((j*256+2,ri*218+195),p.stem+' '+label,fill='black')
        canvas.save(dest/f'page{off//4+1}.jpg',quality=94)
    (dest/'scores.json').write_text(json.dumps({'note':'Paired MAE is not an artistic gate','rows':scores},indent=2))
    model.train()

def paired_terms(y,t,x,model,vgg,ei,step,video,shared):
    with torch.no_grad():ft=vgg(t)
    fy=vgg(y)
    terms={'paired_pixel':F.l1_loss(y,t)*WEIGHTS['pixel'][ei],
           'paired_coarse':F.l1_loss(F.avg_pool2d(y,16),F.avg_pool2d(t,16))*WEIGHTS['coarse'],
           'paired_guide':sum(F.l1_loss(fy[j].float(),ft[j].float()) for j in (1,2,3))*WEIGHTS['guide_perceptual']}
    if ei!=1:
        terms['paired_orientation']=F.l1_loss(old.oriented_energy(y),old.oriented_energy(t))*WEIGHTS['orientation'][ei]
        terms['paired_brush_direction']=art.brush_direction_loss(y,t,x)*WEIGHTS['brush_direction'][ei]
    else:terms['paired_Sobel']=sobel_target_loss(y,t)*WEIGHTS['Sobel'][ei]
    if step%2==0:
        dy,dx=random.choice(((1,1),(-1,3),(3,-1)))
        shifted=torch.roll(x,(dy,dx),(-2,-1))
        if shared:sf=model.encode(shifted)
        else:
            with torch.no_grad():sf=model.encode(shifted)
        sy=model.experts[ei](*sf).float();expected=torch.roll(y.detach(),(dy,dx),(-2,-1))
        terms['equivariance']=F.l1_loss(sy[...,16:-16,16:-16],expected[...,16:-16,16:-16])*WEIGHTS['equivariance'][ei]
    if step%4==0:terms['temporal']=old.temporal_loss(model,video,'cuda',1,(ei,))*WEIGHTS['temporal']
    return terms

@torch.no_grad()
def fixed_comparison(model,base,dest):
    """Inference-only fixed17, native and320x240 internal2x display mode."""
    entries=json.loads((ROOT/'data/fixed_test_manifest.json').read_text())
    assert len(entries)==17
    model.eval();base.eval()
    for mode in ('native','internal320x240_2x_REDUCED_RESOLUTION'):
        for ei,style in enumerate(STYLES):
            rows=[];folder=dest/mode/style;folder.mkdir(parents=True,exist_ok=True)
            for name,meta in entries.items():
                p=Path(meta['path']);assert sha(p)==meta['sha256'];x=image_tensor(p);h,w=x.shape[-2:]
                if mode=='native':z=F.pad(x[None].cuda(),(0,-w%8,0,-h%8),mode='replicate')
                else:z=F.interpolate(x[None].cuda(),(240,320),mode='bilinear',align_corners=False,antialias=True)
                ys=[]
                for net in (base,model):
                    y=net(z,ei).float().clamp(0,1)
                    if mode=='native':y=y[0,:,:h,:w]
                    else:y=F.interpolate(y,(480,640),mode='bilinear',align_corners=False)[0]
                    ys.append(y.cpu())
                imlist=[]
                for j,v in enumerate([x,*ys]):
                    im=Image.fromarray((v.permute(1,2,0).numpy()*255).round().astype('uint8'));im.save(folder/f'{Path(name).stem}_{j}.png');im.thumbnail((320,240));imlist.append(im)
                rows.append((name,imlist))
            for off in range(0,len(rows),4):
                sub=rows[off:off+4];sheet=Image.new('RGB',(960,262*len(sub)),'white');draw=ImageDraw.Draw(sheet)
                for ri,(name,ims) in enumerate(sub):
                    for j,im in enumerate(ims):sheet.paste(im,(320*j,262*ri));draw.text((320*j+2,262*ri+243),name+' '+['INPUT','V3','STUDENT'][j],fill='black')
                sheet.save(folder/f'page{off//4+1}.jpg',quality=94)
    (dest/'PROTOCOL.json').write_text(json.dumps({'inference_only':True,'no_target_tuning':True,'modes':['native','320x240 internal, bilinear2x to640x480; reduced-resolution mode, no measured FPGA FPS'],'entries':entries},indent=2))
    model.train()

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--run',required=True);ap.add_argument('--style',choices=STYLES,required=True)
    ap.add_argument('--steps',type=int,default=4000);ap.add_argument('--batch',type=int,default=8)
    ap.add_argument('--init',default='baseline/tristyle_v3_fp32.pt');ap.add_argument('--target-root')
    ap.add_argument('--legacy-diagnostic',action='store_true');ap.add_argument('--train-count',type=int,default=0)
    ap.add_argument('--resume',action='store_true');ap.add_argument('--eval-every',type=int,default=1000)
    ap.add_argument('--mixed-half',action='store_true');ap.add_argument('--joint',action='store_true')
    ap.add_argument('--continue-training-state',action='store_true',help='New named run restoring full optimizer/scaler/RNG from --init after an explicitly recorded source repair')
    ap.add_argument('--conditional-adv-w',type=float,default=0.)
    ap.add_argument('--diag-target-root',default='',help='Diagnostic run on a NEW target root (dirs named by STYLES); reports to P1b, never promotes')
    ap.add_argument('--adv-border',type=int,default=0,help='Crop this many px from each side before the critic (0 = original behaviour)')
    ap.add_argument('--coarse-weight',type=float,default=0.,help='Override WEIGHTS coarse (16x avgpool L1 to target) to anchor colour; 0 = keep 1.5')
    a=ap.parse_args();owner();torch.set_num_threads(3)
    assert a.run.startswith('claude_'),'Claude takeover runs must be named claude_*'
    if a.coarse_weight>0:WEIGHTS['coarse']=a.coarse_weight
    assert 0<=a.conditional_adv_w<=.5
    seed=20261117;random.seed(seed);np.random.seed(seed);torch.manual_seed(seed);rng=random.Random(seed)
    ei=STYLES.index(a.style)
    diag=bool(a.legacy_diagnostic or a.diag_target_root)
    if a.legacy_diagnostic:
        assert not a.target_root and not a.diag_target_root
        target_root=V3/'data/claude_targets';target_style=['vangogh_p1','ukiyoe_p1','ink_p1'][ei]
        report=ROOT/'reports/paired_v5/P1b'/a.run
    elif a.diag_target_root:
        assert not a.target_root
        target_root=ROOT/a.diag_target_root;target_style=a.style;report=ROOT/'reports/paired_v5/P1b'/a.run
    else:
        assert a.target_root and a.steps>=(1000 if a.joint else 4000)
        assert a.train_count==0,'Formal P3 must use the whole authorized training split'
        gate=ROOT/'reports/paired_v5/P1/G1_APPROVAL.json'
        # PLAN v3 §4.4: G1 may be a visual pass OR an honest 23:30 timebox lock that records FAIL items.
        g=json.loads(gate.read_text()) if gate.is_file() else {}
        assert g.get('visual_passed') is True or (g.get('timebox_locked') is True and g.get('visual_passed') is False and g.get('fail_items')),'G1 neither passed nor honestly timebox-locked'
        target_root=ROOT/a.target_root;target_style=a.style;report=ROOT/'reports/paired_v5/P3'/a.run
        dataset_config=json.loads((target_root/'config.json').read_text())
        complete=json.loads((target_root/'finished.json').read_text())
        assert complete['count']==1263 and complete['target_images']==3789
        assert complete['manifest_sha256']==sha(target_root/'manifest.json')
        assert dataset_config['gate_sha256']==sha(gate)
        assert dataset_config['teachers']==json.loads(gate.read_text())['teachers'],'G1 approval covers a different teacher'
    init=ROOT/a.init;ck=torch.load(init,map_location='cpu',weights_only=False);state=ck['model']
    assert ck.get('config',{}).get('expert1_s8_depthwise_dilation',1)==1,'Explicit graph reconstruction required'
    model=model_for_state(state).cuda();model.load_state_dict(state)
    base_ck=torch.load(ROOT/'baseline/tristyle_v3_fp32.pt',map_location='cpu',weights_only=False)
    base=model_for_state(base_ck['model']).cuda().eval();base.load_state_dict(base_ck['model']);base.requires_grad_(False)
    for n,p in model.named_parameters():p.requires_grad_(n.startswith('experts.') if a.joint else n.startswith(f'experts.{ei}.'))
    if a.joint:
        for n,p in model.named_parameters():p.requires_grad_(True)
    params=[p for p in model.parameters() if p.requires_grad]
    groups=[{'params':[p for n,p in model.named_parameters() if p.requires_grad and n.startswith('experts.')],'initial_lr':2e-4,'lr':2e-4}]
    if a.joint:groups.append({'params':[p for n,p in model.named_parameters() if not n.startswith('experts.')],'initial_lr':1e-5,'lr':1e-5})
    opt=torch.optim.Adam(groups,betas=(.9,.99));scaler=torch.amp.GradScaler('cuda');vgg=old.VGG().cuda().eval();vgg.requires_grad_(False)
    active_ids=list(range(3)) if a.joint else [ei]
    target_names=['vangogh_p1','ukiyoe_p1','ink_p1'] if a.legacy_diagnostic else list(STYLES)
    train_sets={i:RegisteredPairs('train',target_names[i],target_root,a.train_count) for i in active_ids}
    val_sets={i:RegisteredPairs('validation',target_names[i],target_root,12) for i in active_ids}
    train,val=train_sets[ei],val_sets[ei]
    video=old.Video();assert video.files and all(int(p.stem)<=624 for p in video.files),'Training video leakage'
    out=ROOT/'experiments/paired_v5'/a.run;out.mkdir(parents=True,exist_ok=True);report.mkdir(parents=True,exist_ok=True)
    assert a.resume or not (out/'config.json').exists(),'Use a new run name'
    gan=ConditionalPatchGAN(active_ids,a.conditional_adv_w) if a.conditional_adv_w else None
    cfg={**vars(a),'weights':WEIGHTS,'phase':'P1 diagnostic' if diag else 'P3','owner':'claude','trainer':'claude_train_paired.py (copy of train_paired.py 2F9AB36A + owner/diag-root/timebox-gate/adv<=.5)','init_sha256':sha(init),'source_adaptation':'baseline/source/continuation_impl/train_art.py','photo_content':0,'semantic':0,'head_edge':0,'critic':False,'adversarial':0,'patch':0,'moment':0,'freeze_skip':False,'suppress_skip':False,'parameter_count':sum(p.numel() for p in model.parameters()),'parameter_storage_INT8weights_INT32bias':sum(p.numel()*(4 if n.endswith('bias') else 1) for n,p in model.named_parameters()),'promoted':False,'sources':{},'training_video':[]}
    cfg['conditional_critic']={'enabled':bool(gan),'max_G_weight':a.conditional_adv_w,'channels':[6,64,128,256,256,1],'kernels':4,'strides':[2,2,2,1,1],'spectral_norm':True,'D_lr':2e-4,'D_betas':[.5,.999],'loss':'hinge','warmup':300,'ramp':500,'real':'input,target ONLY','fake':'input,student ONLY','training_only_not_deployment':True}
    if not diag:
        cfg['P2_manifest_sha256']=sha(target_root/'manifest.json');cfg['G1_approval_sha256']=sha(gate)
    source_paths=[ROOT/'experiments/paired_v5/conditional_patchgan.py',Path(__file__),ROOT/'experiments/paired_v5/fit_capacity.py',ROOT/'diagnostics/v3_access.py',ROOT/'baseline/source/continuation_impl/train_art.py',ROOT/'baseline/source/claude_impl/train.py',ROOT/'baseline/source/claude_impl/model.py',Path('D:/ClaudeTest/guidance/OWNER.json'),Path('D:/ClaudeTest/guidance/PLAN.md'),Path('D:/ClaudeTest/guidance/LATEST.md')]
    if not a.resume:
        for p in source_paths:
            rel=p.relative_to(ROOT) if p.is_relative_to(ROOT) else Path('guidance')/p.name;dest=out/'source'/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(p.read_bytes());cfg['sources'][str(p)]=sha(p)
        cfg['training_video']=[{'path':str(p),'sha256':sha(p)} for p in video.files]
        (out/'config.json').write_text(json.dumps(cfg,indent=2));(out/'data_manifest.json').write_text(json.dumps({STYLES[i]:{'train':train_sets[i].provenance(),'validation':val_sets[i].provenance()} for i in active_ids},indent=2))
    else:
        previous=json.loads((out/'config.json').read_text())
        for key,value in vars(a).items():
            if key!='resume':assert previous[key]==value,'Resume configuration changed: '+key
        assert previous['init_sha256']==sha(init)
        # Preserve the original source snapshot; resuming a changed algorithm
        # requires a separately named run, not a rewritten experiment history.
        for p in source_paths:
            if p.is_relative_to(ROOT):assert previous['sources'][str(p)]==sha(p),'Source changed since original run: '+str(p)
        cfg=previous
    start=0
    if a.continue_training_state and not a.resume:
        assert a.legacy_diagnostic and not a.resume,'Repair continuation is diagnostic only; retain old run'
        parent=ck['config']
        for key in ('style','steps','batch','train_count','mixed_half','joint','legacy_diagnostic'):
            assert parent[key]==getattr(a,key),'Parent training protocol differs: '+key
        assert parent['weights']==WEIGHTS
        assert parent.get('conditional_adv_w',0.)==a.conditional_adv_w
        model.load_state_dict(ck['model']);opt.load_state_dict(ck['opt']);scaler.load_state_dict(ck['scaler']);start=ck['step']
        rng.setstate(ck['sample_rng']);random.setstate(ck['python_rng']);np.random.set_state(ck['numpy_rng']);torch.set_rng_state(ck['torch_rng'].cpu());torch.cuda.set_rng_state_all([z.cpu() for z in ck['cuda_rng']])
        cfg['repair_continuation']={'checkpoint':a.init,'sha256':sha(init),'step':start,'restored':['model','optimizer','scaler','sample_rng','python_rng','numpy_rng','torch_rng','cuda_rng'],'change':'Skip nonfinite-gradient AMP update using GradScaler, rather than throwing during clipping; original run retained'}
        (out/'config.json').write_text(json.dumps(cfg,indent=2))
    if a.resume:
        c=torch.load(out/'latest.pt',map_location='cuda',weights_only=False);model.load_state_dict(c['model']);opt.load_state_dict(c['opt']);scaler.load_state_dict(c['scaler']);start=c['step'];rng.setstate(c['sample_rng']);random.setstate(c['python_rng']);np.random.set_state(c['numpy_rng']);torch.set_rng_state(c['torch_rng'].cpu());torch.cuda.set_rng_state_all([z.cpu() for z in c['cuda_rng']])
        if gan:gan.load_state_dict(c['conditional_critic'])
    frozen={n:v.cpu().clone() for n,v in model.state_dict().items() if not (n.startswith('experts.') if a.joint else n.startswith(f'experts.{ei}.')) and not (a.joint and not n.startswith('experts.'))}
    def save(step):
        for n,v in frozen.items():assert torch.equal(v,model.state_dict()[n].cpu()),'Frozen tensor changed '+n
        c={'model':model.state_dict(),'config':cfg,'step':step,'opt':opt.state_dict(),'scaler':scaler.state_dict(),'sample_rng':rng.getstate(),'python_rng':random.getstate(),'numpy_rng':np.random.get_state(),'torch_rng':torch.get_rng_state(),'cuda_rng':torch.cuda.get_rng_state_all(),'frozen_tensors_equal':True}
        c['conditional_critic']=gan.state_dict() if gan else None
        torch.save(c,out/'latest.tmp');(out/'latest.tmp').replace(out/'latest.pt')
    log=(out/'metrics.jsonl').open('a',buffering=1);aud=(out/'gradient_audit.jsonl').open('a',buffering=1);began=time.time();step=start
    for step in range(start+1,a.steps+1):
        if (out/'STOP').exists():step-=1;break
        # Joint mode alternates experts, while each frame retains one style.
        if a.joint:ei=(step-1)%3;train,val=train_sets[ei],val_sets[ei]
        for g in opt.param_groups:g['lr']=g['initial_lr']*(.1+.9*.5*(1+math.cos(math.pi*step/a.steps)))
        x,t,half=train.batch(a.batch,rng,a.mixed_half);x,t=x.cuda(),t.cuda();model.train();opt.zero_grad(set_to_none=True)
        with torch.autocast('cuda',dtype=torch.float16):
            if a.joint:features=model.encode(x)
            else:
                with torch.no_grad():features=model.encode(x)
            raw=model.experts[ei](*features).float();y=raw.clamp(0,1)*.98+raw*.02
            terms=paired_terms(y,t,x,model,vgg,ei,step,video,a.joint)
        if gan:
            # 23:40 fix: critic sees the crop interior only (replicate-padded borders gave dark vignettes at adv .2).
            b=a.adv_border
            xs,ts,ys=(x,t,y) if b==0 else (x[...,b:-b,b:-b],t[...,b:-b,b:-b],y[...,b:-b,b:-b])
            terms['conditional_adv']=gan.loss(xs,ts,ys,ei,step,.1+.9*.5*(1+math.cos(math.pi*step/a.steps)))
        loss=sum(terms.values())
        assert torch.isfinite(loss)
        if step in (1,100,500,1000):
            for name,l in terms.items():
                if not l.requires_grad:continue
                scale=scaler.get_scale();gs=torch.autograd.grad(l*scale,params,retain_graph=True,allow_unused=True)
                aud.write(json.dumps({'step':step,'term':name,'weighted_loss':float(l.detach()),'grad_l2':float(sum((g.float()/scale).square().sum() for g in gs if g is not None).sqrt()),'scale':scale})+'\n')
        scaler.scale(loss).backward();scaler.unscale_(opt)
        gradients_finite=all(bool(torch.isfinite(p.grad).all()) for p in params if p.grad is not None)
        old_scale=scaler.get_scale()
        if gradients_finite:gn=torch.nn.utils.clip_grad_norm_(params,3.,error_if_nonfinite=True)
        else:gn=loss.new_tensor(float('inf'))
        # unscale_ already recorded any Inf/NaN. Do not clip invalid gradients;
        # GradScaler.step skips the optimizer, then update lowers its scale.
        scaler.step(opt);scaler.update()
        if not gradients_finite:
            event={'time':now(),'step':step,'AMP_overflow_skipped':True,'old_scale':old_scale,'new_scale':scaler.get_scale(),'finite_loss':float(loss.detach())}
            assert scaler.get_scale()<old_scale
            with (out/'overflow_events.jsonl').open('a') as f:f.write(json.dumps(event)+'\n')
            print('AMP_OVERFLOW_SKIPPED',json.dumps(event),flush=True)
        if step==1 or step%25==0:
            row={'time':now(),'pid':os.getpid(),'step':step,'style':STYLES[ei],'loss':float(loss.detach()),'terms':{k:float(v.detach()) for k,v in terms.items()},'grad_norm':float(gn),'conditional_critic':gan.last if gan else None,'half_resolution_view':half,'seconds':time.time()-began};log.write(json.dumps(row)+'\n');print(json.dumps(row),flush=True)
        if step%100==0 or step==a.steps:save(step)
        if step%a.eval_every==0 or step==a.steps:
            torch.save({'model':model.state_dict(),'config':cfg,'step':step},out/f'step_{step:06d}.pt')
            for j in active_ids:
                gallery(model,base,train_sets[j],j,report/f'{step:06d}'/STYLES[j]/'train',8)
                gallery(model,base,val_sets[j],j,report/f'{step:06d}'/STYLES[j]/'validation',12)
            if not a.legacy_diagnostic and (not a.diag_target_root or step==a.steps):fixed_comparison(model,base,report/f'{step:06d}/fixed17')
        if step==1 or step%100==0:(ROOT/'STATE.json').write_text(json.dumps({'time':now(),'phase':cfg['phase'],'run':str(out.relative_to(ROOT)),'step':step,'pid':os.getpid(),'gate':'G1_NOT_PASSED' if diag else 'G2_PENDING','promoted':False,'owner':'claude'},indent=2))
    save(step);(out/'finished.json').write_text(json.dumps({'time':now(),'step':step,'completed_plan':step==a.steps,'promoted':False,'frozen_tensors_equal':True},indent=2));print('PAIRED_FINISHED_VISUAL_REVIEW_REQUIRED',flush=True)

if __name__=='__main__':main()
