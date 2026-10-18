"""Inspect actual pilot gradients and decoder-route reliance, no weight update."""
import json,pathlib,sys,time
import torch
from torch.nn import functional as F
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'experiments'));sys.path.insert(0,str(ROOT/'diagnostics'))
from style_pilot import ContentMask,standardized,flow_continuity,video_loss
from v3_access import old,STYLES
from model_v4_init_v2 import V4InitV2
from art_objectives import RealArtBank

def group(name):
 if name.startswith('detail.'):return 'shared_fullres_detail'
 if not name.startswith('experts.'):return 'shared_encoder'
 if '.head.' in name:return 'expert_fullres_head'
 if '.context.' in name or '.in16.' in name:return 'expert_lowres_context'
 return 'expert_multiscale_decoder'

def main():
 torch.set_num_threads(3);torch.manual_seed(20261017);dev='cuda';out=ROOT/'reports/pilot_realart_01/gradient_audit';out.mkdir(parents=True,exist_ok=True)
 ck=torch.load(ROOT/'experiments/pilot_realart_01/step_001800.pt',map_location=dev,weights_only=False);m=V4InitV2(identity_head=True).to(dev);m.load_state_dict(ck['model']);m.eval();vgg=old.VGG().to(dev).eval();bank=RealArtBank(vgg,dev,ROOT/'data/realart_shallow_bank_v1.pt');video=old.Video()
 ds=ContentMask();x,mask=ds[8];x,mask=x[None].to(dev),mask[None].to(dev);rows=[]
 for style,s in enumerate(STYLES):
  y=m(x,style);fy=vgg(y);fx=[f.detach() for f in vgg(x)];tex,tone=bank.loss(fy,x,s);content=sum(F.l1_loss(standardized(fy[j]),standardized(fx[j])) for j in (2,3));semantic=y.new_zeros(())
  for j in (2,3):
   mm=F.interpolate(mask,size=fy[j].shape[-2:],mode='area');semantic+=((standardized(fy[j])-standardized(fx[j])).abs()*mm).sum()/(mm.sum()*fy[j].shape[1]+1e-5)
  terms={'real_patch':tex*4,'local_tone':tone*.5,'deep_content':content*[.35,.5,.5][style],'head_semantic':semantic*.15,'temporal':video_loss(m,video,style,dev)*.2}
  if style==0:terms['flow_continuity']=flow_continuity(y,x)*.2
  params=[(n,p) for n,p in m.named_parameters() if not n.startswith('experts.') or n.startswith('experts.'+str(style)+'.')]
  vectors={};groups={}
  for name,loss in terms.items():
   gs=torch.autograd.grad(loss,[p for n,p in params],retain_graph=True,allow_unused=True);vec=[];gn={}
   for (pn,p),g in zip(params,gs):
    g=torch.zeros_like(p) if g is None else g;gn[group(pn)]=gn.get(group(pn),0)+float(g.square().sum());vec.append(g.flatten())
   vectors[name]=torch.cat(vec);groups[name]={k:v**.5 for k,v in gn.items()}
  cs={a+'__'+b:float(F.cosine_similarity(vectors[a],vectors[b],dim=0)) for a in vectors for b in vectors if a<b}
  normal=y.detach();ablations={}
  for route in ('context','detail'):
   def hook(module,args):
    z=args[0].clone();z[:,:8 if route=='context' else 0]=0 if route=='context' else z[:,:0]
    if route=='detail':z[:,8:]=0
    return (z,)
   h=m.experts[style].head.fuse.conv.register_forward_pre_hook(hook)
   with torch.no_grad():z=m(x,style)
   h.remove();ablations[route+'_zeroed_output_MAE']=float((z-normal).abs().mean())
  row={'style':s,'checkpoint_step':ck['step'],'TRAINING_input':ds.files[8].stem,'per_loss_value':{k:float(v.detach()) for k,v in terms.items()},'gradient_L2_by_parameter_group':groups,'gradient_cosines':cs,'ablations':ablations,'normal_vs_input_MAE':float((normal-x).abs().mean()),'mean_RGB':normal.mean((0,2,3)).tolist()};rows.append(row);print(json.dumps(row),flush=True)
 (out/'result.json').write_text(json.dumps({'kind':'single TRAINING crop diagnostic, not artistic metric or complete causal audit','rows':rows},indent=1))
if __name__=='__main__':main()
