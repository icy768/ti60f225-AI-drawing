"""Checks that catch broken local matching, spatial alignment, and export schema."""
import torch
from art_material_v7 import PatchBank,material_target,shift_consistency
from tinystyle import TinyStyleNet,macs_per_pixel

torch.set_num_threads(4);torch.manual_seed(1)
for x in (torch.zeros(1,3,64,64),torch.ones(1,3,64,64),torch.rand(2,3,64,64)):
    for s in (1,2):
        y=material_target(x,s)
        assert y.shape==x.shape and torch.isfinite(y).all() and y.min()>=0 and y.max()<=1
f=torch.rand(1,8,32,32)
bank=PatchBank([[None,f]])
assert bank.loss(f).item()<1e-10
q=(f+.2).clone().requires_grad_();loss=bank.loss(q);loss.backward()
assert torch.isfinite(q.grad).all() and q.grad.abs().sum()>0
class Identity:
    def __call__(self,x,style):return x
x=torch.rand(1,3,80,96)
for step in (0,4,8,12):assert shift_consistency(Identity(),x,torch.tensor([0]),x,step).item()==0
net=TinyStyleNet(C=24,Fc=16,n_res=4,n_styles=3,norm='in',block='dw1')
assert sum(p.numel() for p in net.parameters())==11028
assert macs_per_pixel(net.specs)[0]*640*480==339148800
print('PASS: target range, patch identity/gradient, four shift alignments, frozen graph cost')
