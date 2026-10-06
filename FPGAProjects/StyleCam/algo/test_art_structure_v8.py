"""Validate sparse-region supervision and immutable deployment graph costs."""
import torch
import torch.nn.functional as F
from art_structure_v8 import target,separated_loss,spatial_covariance,covariance_loss
from tinystyle import TinyStyleNet,macs_per_pixel

torch.set_num_threads(4);torch.manual_seed(4)
x=torch.rand(2,3,64,64);x[:,:,8:28,8:28]=.03;x[:,:,36:58,36:58]=.95
for s in [1,2]:
    t=target(x,s)
    assert torch.isfinite(t).all() and t.min()>=0 and t.max()<=1
    y=t.clone().requires_grad_();loss=sum(separated_loss(y,t))
    assert loss.item()==0
    loss.backward();assert torch.isfinite(y.grad).all()
    blurred=F.avg_pool2d(F.pad(t,(3,)*4,mode='reflect'),7,1)
    assert sum(separated_loss(blurred,t)).item()>0
    if s==2:
        assert t[:,:,12:24,12:24].mean()<.25
        assert t[:,:,42:52,42:52].mean()>.9
f=torch.rand(2,64,32,32,requires_grad=True)
cs=[v.detach() for v in spatial_covariance(f)]
loss=covariance_loss(f,cs);assert loss.item()<1e-8;loss.backward()
assert torch.isfinite(f.grad).all()
n=TinyStyleNet(C=24,Fc=16,n_res=4,n_styles=3,norm='in',block='dw1')
assert sum(p.numel() for p in n.parameters())==11028
assert macs_per_pixel(n.specs)[0]*640*480==339148800
print('PASS: dark/paper separation, finite gradients, blur detection, covariance identity, deployment costs')
