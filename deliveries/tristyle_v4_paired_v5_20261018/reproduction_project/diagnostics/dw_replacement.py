"""Read-only V3 full-resolution DW rank alternatives; no training or candidate promotion."""
import copy,datetime,json,math,pathlib,time
import numpy as np,torch
from torch import nn
from PIL import Image,ImageDraw
from v3_access import ROOT,V3,model_for_state,STYLES
torch.set_num_threads(3);torch.manual_seed(17);dev='cuda' if torch.cuda.is_available() else 'cpu'
out=ROOT/'reports/dw_replacement';out.mkdir(parents=True,exist_ok=True)
state=torch.load(ROOT/'baseline/tristyle_v3_fp32.pt',map_location='cpu',weights_only=False)['model'];base=model_for_state(state).eval();base.load_state_dict(state)
class RankDW(nn.Module):
 def __init__(self,old,rank):
  super().__init__();w=old.weight.detach()[:,0].double();u,s,vh=torch.linalg.svd(w);c,k=w.shape[0],w.shape[-1];self.paths=nn.ModuleList()
  for r in range(rank):
   h=nn.Conv2d(c,c,(1,k),padding=(0,k//2),groups=c,bias=False);v=nn.Conv2d(c,c,(k,1),padding=(k//2,0),groups=c,bias=False)
   h.weight.data.copy_((vh[:,r]*s[:,r].sqrt()[:,None])[:,None,None,:].float());v.weight.data.copy_((u[:,:,r]*s[:,r].sqrt()[:,None])[:,None,:,None].float());self.paths.append(nn.Sequential(h,v))
  self.bias=nn.Parameter(old.bias.detach().clone())
 def forward(self,x):return sum(p(x) for p in self.paths)+self.bias[None,:,None,None]
checks=[]
for i,e in enumerate(base.experts):
 old=e.dw1.conv;k=old.kernel_size[0];full=RankDW(old,k);x=torch.randn(1,old.in_channels,24,32)
 with torch.no_grad():a=old(x);b=full(x)
 err=float((a-b).abs().max());assert err<1e-4,(i,err)
 checks.append({'style':STYLES[i],'full_rank':k,'random_layer_maxabs':err})
models={'V3':base.to(dev)}
for rank in (1,2,4):
 m=model_for_state(state);m.load_state_dict(state)
 for e in m.experts:e.dw1.conv=RankDW(e.dw1.conv,rank)
 models['DW_rank'+str(rank)]=m.to(dev).eval()
 # Only weight/bias payload, metadata is not this number.
print('MODELS_READY',flush=True)
rows=[];files=sorted((V3/'data/test').glob('*.png'));grids={s:[] for s in STYLES}
with torch.inference_mode():
 for p in files:
  im=Image.open(p).convert('RGB');im=im.crop((0,0,im.width//8*8,im.height//8*8));a=np.array(im,copy=True);x=torch.from_numpy(a).permute(2,0,1)[None].float().to(dev)/255
  for ei,style in enumerate(STYLES):
   outputs={}
   for name,m in models.items():
    t=time.perf_counter();y=m(x,ei).clamp(0,1)
    if dev=='cuda':torch.cuda.synchronize()
    dt=time.perf_counter()-t;raw=(y[0].permute(1,2,0)*255).round().to(torch.uint8).cpu().numpy();outputs[name]=raw;folder=out/name;folder.mkdir(exist_ok=True);Image.fromarray(raw).save(folder/f'{p.stem}_{style}.png')
    if name!='V3':
     d=(raw.astype(float)-outputs['V3'].astype(float))/255;rows.append({'scene':p.stem,'style':style,'replacement':name,'same_input_size':list(im.size),'PSNR_vs_V3_functional_retention_only':-10*math.log10(max(float((d*d).mean()),1e-12)),'host_seconds':dt})
   grids[style].append((p.stem,[a]+list(outputs.values())))
  print('DW_SCENE',p.stem,flush=True)
for style,entries in grids.items():
 w,h=256,208;sheet=Image.new('RGB',(5*w,len(entries)*(h+22)),'white');draw=ImageDraw.Draw(sheet)
 for row,(name,ims) in enumerate(entries):
  for col,a in enumerate(ims):
   p=Image.fromarray(a);p.thumbnail((w,h));sheet.paste(p,(w*col,(h+22)*row));draw.text((w*col+3,(h+22)*row+h+2),name+' '+['INPUT','V3','DW-rank1','DW-rank2','DW-rank4'][col],fill='black')
 sheet.save(out/f'{style}_actual17.jpg',quality=92)
 # Center crops show real pixel texture without sharpening.
 sheet=Image.new('RGB',(5*192,len(entries)*(192+18)),'white');draw=ImageDraw.Draw(sheet)
 for row,(name,ims) in enumerate(entries):
  for col,a in enumerate(ims):
   hh,ww=a.shape[:2];p=Image.fromarray(a).crop(((ww-192)//2,(hh-192)//2,(ww+192)//2,(hh+192)//2));sheet.paste(p,(192*col,210*row));draw.text((192*col+2,210*row+193),name+' '+['input','V3','rank1','rank2','rank4'][col],fill='black')
 sheet.save(out/f'{style}_native_crops17.jpg',quality=94)
report={'time':datetime.datetime.now().astimezone().isoformat(),'status':'MEASURED actual17 scenes, frozen V3 vs untrained separable-DW approximations','layer_equivalence_full_rank':checks,'rows':rows,'model_parameter_counts':{k:sum(p.numel() for p in m.parameters()) for k,m in models.items()},'scope':'Pure functional/cost ablation; retention PSNR is NOT style quality. Not a trained V4, quantized export, synthesis or FPGA fps. No hidden activation between factorized kernels.'}
(out/'result.json').write_text(json.dumps(report,indent=1),encoding='utf-8');print('DW_REPLACEMENT_DONE',flush=True)
