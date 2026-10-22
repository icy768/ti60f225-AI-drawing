from pathlib import Path
import torch,numpy as np,sys,json,hashlib
R=Path(__file__).resolve().parent;sys.path.insert(0,str(R/'algo'))
import golden
from r44_forward import TinyStyleNet,CONTRACT,QCfg
torch.set_num_threads(4);torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
ck=torch.load(R/'runs/art_styles_c24_v21b_ukiyoe_qat900_soft15/student.pt',map_location='cpu',weights_only=False)
QCfg.enabled=True;QCfg.observe=False
rows=[]
for device in ['cpu']+(['cuda'] if torch.cuda.is_available() else []):
 net=TinyStyleNet(**ck['cfg']).to(device).eval();net.load_state_dict(ck['sd'])
 im=np.random.default_rng(44).integers(0,256,(32,48,3),dtype=np.uint8)
 x=torch.from_numpy(im).permute(2,0,1)[None].to(device).float()/255
 for si in range(3):
  with torch.no_grad():y=net(x,torch.tensor([si],device=device))
  out=(y[0].permute(1,2,0).cpu().numpy()*255).round().astype(np.uint8)
  ref,_,_=golden.run(CONTRACT,im,si)
  mismatch=int(np.count_nonzero(out!=ref));assert mismatch==0,(device,si,mismatch)
  rows.append({'device':device,'style':si,'mismatch':mismatch})
 net.train();net.zero_grad(set_to_none=True);y=net(x,torch.tensor([0],device=device));y.square().mean().backward()
 assert all(p.grad is not None and torch.isfinite(p.grad).all() for p in net.parameters())
 for k,v in net.state_dict().items():assert torch.equal(v.cpu(),ck['sd'][k]),k
 del net
for ext in ['npz','json']:
 assert (R/f'F0/baseline_reexport.{ext}').read_bytes()==(R/f'audits/v21b_deploy_blob/qparams.{ext}').read_bytes()
data={'pass':True,'cases':rows,'finite_gradients':True,'no_baseline_state_change':True,'baseline_byte_equal':True,'optimizer_restore_possible':'opt' in ck}
(R/'F0/PREFLIGHT.json').write_text(json.dumps(data,indent=2),encoding='utf-8');print(data)
