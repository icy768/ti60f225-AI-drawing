import torch
from integer_reference import IntegerGraph
torch.set_num_threads(4);g=IntegerGraph('deployment_iteration03/tristyle_all.bin');q=torch.jit.load('deployment_iteration03/tristyle_int8.ts')
# ScriptModule hooks are unavailable; load fresh package into eager model.
from export_int8 import load_pack
q=load_pack('deployment_iteration03/tristyle_all.bin');actual={};hooks=[]
for name,m in q.named_modules():
    if isinstance(m,torch.ao.nn.quantized.Conv2d):
        def hook(mod,args,out,key=name):actual[key]=out.int_repr().long()
        hooks.append(m.register_forward_hook(hook))
x=torch.randint(0,256,(1,3,32,40),dtype=torch.uint8);trace={}
with torch.inference_mode():q(x.float()/255,0);g(x,0,trace)
for k,v in actual.items():
    err=(trace[k]-v).abs();print(k,int(err.max()),float(err.float().mean()))
