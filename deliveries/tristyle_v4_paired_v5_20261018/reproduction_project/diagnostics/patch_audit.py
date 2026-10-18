"""Measure V3 top-energy selection bias; propose visually reviewable style-specific strata."""
import datetime,json,pathlib,random
import cv2,numpy as np,torch
from torch.nn import functional as F
from PIL import Image,ImageDraw
from v3_access import ROOT,V3,old,STYLES
torch.set_num_threads(3);torch.manual_seed(20261017);rng=random.Random(20261017)
out=ROOT/'reports/patch_audit';out.mkdir(parents=True,exist_ok=True)
cfg=json.loads((ROOT/'baseline/v3_training_config.json').read_text());dev='cuda' if torch.cuda.is_available() else 'cpu';vgg=old.VGG().to(dev).eval()
def stats(im):
 a=np.asarray(im,dtype=np.float32)/255;g=cv2.cvtColor(a,cv2.COLOR_RGB2GRAY);dx=cv2.Sobel(g,cv2.CV_32F,1,0,ksize=3)/8;dy=cv2.Sobel(g,cv2.CV_32F,0,1,ksize=3)/8
 xx,yy,xy=float((dx*dx).mean()),float((dy*dy).mean()),float((dx*dy).mean());energy=xx+yy
 hsv=cv2.cvtColor(a,cv2.COLOR_RGB2HSV)
 return {'luminance':float(g.mean()),'paper_fraction':float((g>.82).mean()),'dark_fraction':float((g<.28).mean()),'gradient_energy':energy,'coherence':float(np.sqrt((xx-yy)**2+4*xy*xy)/(energy+1e-8)),'saturation':float(hsv[:,:,1].mean()),'lap_gradient_ratio':float(np.abs(cv2.Laplacian(g,cv2.CV_32F)).mean()/(np.sqrt(energy)+1e-6))}
oldrows=[];newbank={}
for style in STYLES:
 candidates=[]
 for rr in cfg['reference_bank'][style]:
  path=V3/rr['path'];im=Image.open(path).convert('RGB');w,h=im.size
  if style=='ink' and h>w*2:im=im.crop((int(w*.12),int(h*.05),int(w*.88),int(h*.95)))
  scale=320/min(im.size);s=im.resize((round(im.width*scale),round(im.height*scale)),Image.Resampling.LANCZOS)
  for pos in (.25,.65):
   l,t=round((s.width-256)*pos),round((s.height-256)*pos);crop=s.crop((l,t,l+256,t+256));a=np.array(crop,copy=True);x=torch.from_numpy(a).permute(2,0,1)[None].float().to(dev)/255
   with torch.no_grad():fs=vgg(x)
   for j in (1,2):
    f=fs[j];u=F.unfold(f,3,padding=1,stride=2).transpose(1,2)[0];ids=torch.randperm(len(u),device=dev)[:1024];d=u[ids].reshape(-1,f.shape[1],9);d=d-d.mean(-1,keepdim=True);energy=d.square().mean((1,2));top=energy.topk(min(80,len(energy))).indices
    support=(18,48)[j-1];jump=(2,4)[j-1];grid=(f.shape[-1]+1)//2
    def rows(indices):
     records=[]
     for n in indices.detach().cpu().tolist():
      flat=int(ids[n]);cy,cx=(flat//grid)*2*jump,(flat%grid)*2*jump;box=(max(0,cx-support//2),max(0,cy-support//2),min(256,cx+support//2),min(256,cy+support//2));p=crop.crop(box)
      if min(p.size)<4:continue
      q=stats(p);q['touches_crop_border']=box[0]==0 or box[1]==0 or box[2]==256 or box[3]==256;records.append(q)
     return records
    pool=rows(torch.arange(len(ids),device=dev));selected=rows(top)
    summarize=lambda rs:{'samples':len(rs),'mean_luminance':float(np.mean([r['luminance'] for r in rs])),'mean_gradient_energy':float(np.mean([r['gradient_energy'] for r in rs])),'paper_dominant_fraction':float(np.mean([r['paper_fraction']>.8 for r in rs])),'dark_dominant_fraction':float(np.mean([r['dark_fraction']>.3 for r in rs])),'border_support_fraction':float(np.mean([r['touches_crop_border'] for r in rs]))}
    oldrows.append({'style':style,'reference':rr['path'],'position':pos,'feature_level':j,'support_approx_pixels':support,'all_random1024':summarize(pool),'top80_energy':summarize(selected)})
  # Strata cover the artwork, rather than only two fixed256 crops.
  scale=min(1.0,1400/max(im.size));big=im.resize((max(128,round(im.width*scale)),max(128,round(im.height*scale))),Image.Resampling.LANCZOS)
  for size in (32,64,128):
   for _ in range(40):
    l=rng.randrange(big.width-size+1);t=rng.randrange(big.height-size+1);p=big.crop((l,t,l+size,t+size));candidates.append({'reference':rr['path'],'box':[l,t,l+size,t+size],'image_scaled_size':list(big.size),'size':size,'stats':stats(p),'image':p})
 q=lambda key,p:float(np.quantile([r['stats'][key] for r in candidates],p))
 if style=='vangogh':
  tests={'continuous_candidate':lambda s:s['coherence']>.35 and q('gradient_energy',.35)<s['gradient_energy']<q('gradient_energy',.9),'layered_texture_candidate':lambda s:s['gradient_energy']>q('gradient_energy',.55) and s['coherence']<.65,'quiet_color_candidate':lambda s:s['gradient_energy']<q('gradient_energy',.35) and s['saturation']>.08}
 elif style=='ukiyoe':
  tests={'flat_color_candidate':lambda s:s['gradient_energy']<q('gradient_energy',.3),'important_boundary_candidate':lambda s:s['coherence']>.35 and s['gradient_energy']>q('gradient_energy',.4),'decoration_candidate':lambda s:q('gradient_energy',.45)<s['gradient_energy']<q('gradient_energy',.85)}
 else:
  tests={'blank_candidate':lambda s:s['paper_fraction']>.8 and s['gradient_energy']<q('gradient_energy',.3),'pale_wash_candidate':lambda s:s['luminance']>.65 and s['dark_fraction']<.04 and s['paper_fraction']<.85,'dense_ink_candidate':lambda s:s['dark_fraction']>.2,'dry_edge_candidate':lambda s:s['paper_fraction']>.2 and s['dark_fraction']>.03 and s['lap_gradient_ratio']>q('lap_gradient_ratio',.6),'wash_edge_candidate':lambda s:q('gradient_energy',.15)<s['gradient_energy']<q('gradient_energy',.5) and s['luminance']>.45 and s['paper_fraction']<.8}
 sheet=Image.new('RGB',(8*128,(len(tests))*154),'white');draw=ImageDraw.Draw(sheet);records=[]
 for row,(tag,test) in enumerate(tests.items()):
  pool=[r for r in candidates if test(r['stats'])];rng.shuffle(pool);sample=pool[:8]
  for col,r in enumerate(sample):
   p=r['image'].resize((128,128),Image.Resampling.NEAREST);sheet.paste(p,(128*col,154*row));draw.text((128*col+2,154*row+130),tag[:20],fill='black');draw.text((128*col+2,154*row+142),'source '+str(r['size'])+'px',fill='black')
   rr={k:v for k,v in r.items() if k!='image'};rr.update(tag=tag,eligible_pool=len(pool));records.append(rr)
  if not sample:draw.text((4,154*row+4),'NO CANDIDATES: '+tag,fill='red')
 sheet.save(out/f'stratified_{style}_CANDIDATES.jpg',quality=95);newbank[style]=records
report={'time':datetime.datetime.now().astimezone().isoformat(),'old_policy':'Approximate image support of actual VGG descriptors, random1024 then top80 energy; reconstruction uses fixed diagnostic RNG, not historical random choices','V3_patch_rows':oldrows,'new_strata':'Heuristic candidate bins only; visual review required before training. Classes such as dry/wet/impasto cannot be certified by these proxy scores. No reference coordinates will be imposed on content.','stratified_candidate_members':newbank}
(out/'audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=1),encoding='utf-8');print('PATCH_AUDIT_DONE',len(oldrows),'reference/crop/level groups',flush=True)
