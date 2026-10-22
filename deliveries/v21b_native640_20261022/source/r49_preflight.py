from pathlib import Path
import sys,json,datetime,hashlib
import torch
R=Path(__file__).resolve().parent;sys.path.insert(0,str(R/'algo'))
from r49_objectives import structure_direction
from r44_forward import TinyStyleNet,QCfg
from train import image_list,CropSet
torch.set_num_threads(4);torch.manual_seed(4400)
rows=[]
for mode in ['constant','random','edge']:
    x=torch.ones(2,3,32,32)*.5 if mode=='constant' else torch.rand(2,3,32,32)
    if mode=='edge':x[:,:,:,:16]=0;x[:,:,:,16:]=1
    y=x.clone().requires_grad_();v=structure_direction(y,x)
    g=torch.autograd.grad(v,y)[0];assert torch.isfinite(v) and torch.isfinite(g).all()
    rows.append(dict(input=mode,loss=float(v),finite_gradient=True))
ck=torch.load(R/'runs/r44_j1_60/student.pt',map_location='cpu',weights_only=False)
net=TinyStyleNet(**ck['cfg']).cuda();net.load_state_dict(ck['sd']);QCfg.enabled=True;QCfg.observe=False
train,held=image_list();assert not set(train)&set(held)
x=next(iter(torch.utils.data.DataLoader(CropSet(train,256),batch_size=1))).cuda().float()/255
y=net(x,torch.tensor([0],device='cuda'));v=structure_direction(y,x);v.backward()
assert torch.isfinite(v) and all(p.grad is None or torch.isfinite(p.grad).all() for p in net.parameters())
rows.append(dict(input='legal_train_crop256_cuda',loss=float(v),finite_gradient=True,optimizer_step=False))
assert all(torch.equal(v.cpu(),ck['sd'][k]) for k,v in net.state_dict().items())
o=R/'R49';o.mkdir(exist_ok=True)
(o/'PREFLIGHT.json').write_text(json.dumps(dict(passed=True,time=datetime.datetime.now().astimezone().isoformat(),rows=rows,parent_sha256=hashlib.sha256((R/'runs/r44_j1_60/student.pt').read_bytes()).hexdigest(),heldout_optimized=False,optimizer_step=False),indent=2),encoding='utf-8')
print('J5 constant/random/edge/CUDA traincrop finite-gradient PASS')
