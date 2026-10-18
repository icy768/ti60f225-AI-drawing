"""Actual weighted V3 gradient probes. No optimizer, updates or test-set training."""
import datetime,hashlib,json,math,pathlib,random,sys,time
import numpy as np,torch
from torch.nn import functional as F
from PIL import Image,ImageDraw
from v3_access import ROOT,V3,art,old,model_for_state,STYLES

torch.set_num_threads(3);torch.manual_seed(20261017);np.random.seed(20261017);random.seed(20261017)
dev='cuda' if torch.cuda.is_available() else 'cpu';out=ROOT/'reports/gradient_audit';out.mkdir(parents=True,exist_ok=True)
cfg=json.loads((ROOT/'baseline/v3_training_config.json').read_text());weights=cfg['weights']
ck=V3/'runs/continuation_final_refine/step_006000.pt';checkpoint=torch.load(ck,map_location='cpu',weights_only=False)
model=model_for_state(checkpoint['model']).to(dev).eval();model.load_state_dict(checkpoint['model'])
# These hooks reproduce the actual final run's blocked skip-weight slices.
if cfg.get('freeze_skip_routes'):art.constrain_content_routes(model,[],256,dev,suppress=False)
vgg=old.VGG().to(dev).eval();bank=art.ArtBank(vgg,dev);video=old.Video()
critics=None
if checkpoint.get('critics'):
 critics=torch.nn.ModuleList([art.StyleCritic(cfg['critic_texture']) for _ in STYLES]).to(dev).eval();critics.load_state_dict(checkpoint['critics'])
 for p in critics.parameters():p.requires_grad_(False)
ds=art.SpatialPaired('train',256,cfg['targets'])
heads=[];others=[]
for stem in ds.stems:
 mp=V3/'data/claude_targets/content_masks/train'/(stem+'.png')
 if mp.exists() and np.array(Image.open(mp)).max()>0:heads.append(stem)
 else:others.append(stem)
pick=lambda a,n:[a[i] for i in np.linspace(0,len(a)-1,min(n,len(a)),dtype=int)]
stems=pick(heads,3)+pick(others,3);assert len(stems)==6
cases=[]
for stem in stems:
 ims=[Image.open(V3/'data/claude_targets'/d/'train'/(stem+'.png')).convert('RGB') for d in ['content']+cfg['targets']]
 w,h=ims[0].size;l,t=(w-256)//2,(h-256)//2
 arr=np.stack([np.array(im.crop((l,t,l+256,t+256)),copy=True) for im in ims]);batch=torch.from_numpy(arr).permute(0,3,1,2)[None].float().to(dev)/255
 mp=V3/'data/claude_targets/content_masks/train'/(stem+'.png');mask=np.array(Image.open(mp).convert('L').crop((l,t,l+256,t+256)),copy=True) if mp.exists() else np.zeros((256,256),np.uint8)
 cases.append((stem,batch,torch.from_numpy(mask)[None,None].float().to(dev)/255,arr))
sheet=Image.new('RGB',(256*4,280*len(cases)),'white');draw=ImageDraw.Draw(sheet)
for i,(stem,_,_,arr) in enumerate(cases):
 for j,a in enumerate(arr):sheet.paste(Image.fromarray(a),(j*256,i*280));draw.text((j*256+4,i*280+258),stem+' '+('INPUT' if j==0 else 'V3 TARGET '+STYLES[j-1]),fill='black')
sheet.save(out/'paired_targets_TRAINING_ONLY.jpg',quality=92)
params=[p for p in model.parameters() if p.requires_grad];names=[n for n,p in model.named_parameters() if p.requires_grad]
groups={}
offset=0
for n,p in zip(names,params):
 parts=n.split('.');group='shared' if parts[0]!='experts' else STYLES[int(parts[1])]+'.'+parts[2]
 groups.setdefault(group,[]).append((offset,offset+p.numel()));offset+=p.numel()
def flat_grad(loss):
 if not loss.requires_grad:return torch.zeros(offset,device=dev)
 gs=torch.autograd.grad(loss,params,retain_graph=True,allow_unused=True)
 return torch.cat([torch.zeros_like(p).flatten() if g is None else g.detach().flatten() for p,g in zip(params,gs)])
def cosine(a,b):return float(torch.dot(a,b)/(a.norm()*b.norm()+1e-20))
rows=[];log=(out/'cases.jsonl').open('a',encoding='utf-8',buffering=1);start=time.time()
for stem,batch,mask,_ in cases:
 for ei,style in enumerate(STYLES):
  x=batch[:,0];target=batch[:,ei+1];raw=model(x,ei);y=raw.clamp(0,1)*.98+raw*.02
  fs=vgg(y)
  with torch.no_grad():fc=vgg(x);ft=vgg(target)
  terms={};coeff={}
  terms['content']=sum(F.l1_loss(art.standardized(fs[j]),art.standardized(fc[j])) for j in (2,3));coeff['content']=weights['content'][ei]
  patch,moment=bank.losses(fs,style);terms.update(patch=patch,moment=moment);coeff.update(patch=weights['patch'][ei]*cfg['patch_scale'],moment=weights['moment'][ei]*cfg['patch_scale'])
  terms['paired_pixel']=F.l1_loss(y,target);coeff['paired_pixel']=weights['pixel'][ei]
  terms['paired_coarse']=F.l1_loss(F.avg_pool2d(y,16),F.avg_pool2d(target,16));coeff['paired_coarse']=weights['coarse']
  terms['guide_perceptual']=sum(F.l1_loss(fs[j],ft[j]) for j in (1,2,3));coeff['guide_perceptual']=weights['guide_perceptual'][ei]
  if ei!=1:
   terms['paired_orientation']=F.l1_loss(old.oriented_energy(y),old.oriented_energy(target));coeff['paired_orientation']=weights['orientation'][ei]
   terms['paired_brush_direction']=art.brush_direction_loss(y,target,x);coeff['paired_brush_direction']=weights['brush_direction'][ei]
  semantic=y.new_zeros(())
  for j in (2,3):
   sm=F.interpolate(mask,size=fs[j].shape[-2:],mode='area');df=(art.standardized(fs[j])-art.standardized(fc[j])).abs();semantic+=((df*sm).sum()/(sm.sum()*fs[j].shape[1]+1e-5))
  terms['semantic_head']=semantic;coeff['semantic_head']=.2
  lum=y.new_tensor([.299,.587,.114]).view(1,3,1,1);yg,xg=(y*lum).sum(1,keepdim=True),(x*lum).sum(1,keepdim=True);edge=y.new_zeros(())
  for dim in (-1,-2):
   yd,xd=yg.diff(dim=dim),xg.diff(dim=dim);ms=mask[...,:-1] if dim==-1 else mask[...,:-1,:];scale=xd.square().mean((2,3),keepdim=True).sqrt().clamp_min(.03);edge+=(((yd-xd)/scale).abs()*ms).sum()/(ms.sum()+1e-5)
  terms['head_edge']=edge;coeff['head_edge']=cfg.get('head_edge_weight',0.)
  if critics is not None:terms['art_critic']=-critics[ei](y).mean();coeff['art_critic']=cfg['adversarial_weight']
  dy,dx=(1,1);sy=model(torch.roll(x,(dy,dx),(-2,-1)),ei);expected=torch.roll(y.detach(),(dy,dx),(-2,-1))
  terms['equivariance']=F.l1_loss(sy[...,16:-16,16:-16],expected[...,16:-16,16:-16]);coeff['equivariance']=weights['equivariance'][ei]
  terms['video_temporal']=old.temporal_loss(model,video,dev,1,(ei,));coeff['video_temporal']=4.0
  grads={k:flat_grad(v*coeff[k]) for k,v in terms.items()};freq={'equivariance':.5,'video_temporal':.25}
  avg={k:g*freq.get(k,1.) for k,g in grads.items()};total=sum(avg.values());artgrad=sum(g for k,g in avg.items() if k in ('patch','moment','art_critic'));pairgrad=sum(g for k,g in avg.items() if k.startswith('paired_') or k=='guide_perceptual');preserve=total-artgrad-pairgrad
  norms={k:float(g.norm()) for k,g in grads.items()};den=sum(norms.values())+1e-20
  part={k:{'weighted_loss':float(terms[k].detach())*coeff[k],'coefficient':coeff[k],'parameter_gradient_norm':norms[k],'share_of_sum_norms':norms[k]/den,'cosine_with_art_objective_gradient':cosine(avg[k],artgrad),'schedule_frequency':freq.get(k,1.),'group_norms':{group:math.sqrt(sum(float(g[a:b].square().sum()) for a,b in slices)) for group,slices in groups.items()}} for k,g in grads.items()}
  row={'stem':stem,'style':style,'mask_fraction':float(mask.mean()),'terms':part,'schedule_average_total_gradient_norm':float(total.norm()),'art_vs_paired_cosine':cosine(artgrad,pairgrad),'art_vs_preserve_cosine':cosine(artgrad,preserve),'art_vs_total_cosine':cosine(artgrad,total),'art_loss_first_order_change_under_total_descent':-float(torch.dot(artgrad,total)),'pairwise_cosines':{a:{b:cosine(avg[a],avg[b]) for b in avg} for a in avg},'seconds':time.time()-start}
  log.write(json.dumps(row)+'\n');rows.append(row);print('GRAD',len(rows),stem,style,'art_vs_pair',round(row['art_vs_paired_cosine'],4),flush=True)
  del fs,fc,ft,terms,grads,avg,total,artgrad,pairgrad,preserve,raw,y,sy,semantic,edge,part
  torch.cuda.empty_cache()
summary={}
for style in STYLES:
 rs=[r for r in rows if r['style']==style];keys=sorted(set(k for r in rs for k in r['terms']))
 summary[style]={'cases':len(rs),'mean_art_vs_paired_cosine':float(np.mean([r['art_vs_paired_cosine'] for r in rs])),'mean_art_vs_preserve_cosine':float(np.mean([r['art_vs_preserve_cosine'] for r in rs])),'art_proxy_increased_under_total_descent_cases':sum(r['art_loss_first_order_change_under_total_descent']>0 for r in rs),'mean_weighted_gradient_norms':{k:float(np.mean([r['terms'][k]['parameter_gradient_norm'] for r in rs if k in r['terms']])) for k in keys}}
report={'time':datetime.datetime.now().astimezone().isoformat(),'checkpoint':str(ck),'checkpoint_sha256':hashlib.sha256(ck.read_bytes()).hexdigest(),'model_point':'actual pre-QAT final6000 student with matching saved critics; compares original weighted training objective locally, not QAT trajectory','training_stems':stems,'test_set_used_for_gradient':False,'optimizer_steps':0,'skip_gradient_masks_reproduced':cfg.get('freeze_skip_routes',False),'schedule':'Equivariance half steps,video temporal quarter steps; all-active norms and schedule-scaled vector dot products separately recorded','interpretation':'Local gradients of proxy objectives, not proof of artistic improvement or entire training causality. Sum-of-norm shares are not additive learning percentages. New deterministic reference-bank sampling reproduces policy, not historical random patch coordinates.','summary':summary}
(out/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
