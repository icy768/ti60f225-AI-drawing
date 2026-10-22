"""J5 training-only local axial direction alignment; no deployment graph change."""
import torch
import torch.nn.functional as F

def smooth(x, k):
    return F.avg_pool2d(F.pad(x, (k//2,)*4, mode='reflect'), k, stride=1)

def tensor_axis(z):
    dx=F.pad((z[:,:,:,2:]-z[:,:,:,:-2])*.5,(1,1,0,0),mode='replicate')
    dy=F.pad((z[:,:,2:,:]-z[:,:,:-2,:])*.5,(0,0,1,1),mode='replicate')
    xx,xy,yy=smooth(dx*dx,9),smooth(dx*dy,9),smooth(dy*dy,9)
    a,b=xx-yy,2*xy
    # Epsilon under sqrt keeps constant/isotropic inputs differentiable.
    norm=torch.sqrt(a.square()+b.square()+1e-12)
    return a/norm,b/norm,norm,xx+yy

def structure_direction(y,x):
    weights=y.new_tensor([.299,.587,.114])[None,:,None,None]
    out=(y*weights).sum(1,keepdim=True)
    inp=(x.detach()*weights).sum(1,keepdim=True)
    u,v,_,_=tensor_axis(out-smooth(out,9))
    with torch.no_grad():
        a,b,n,e=tensor_axis(smooth(inp,7))
        coherence=(n-1e-6).clamp_min(0)/(e+1e-6)
        reliability=(e/(e+1e-4))*coherence.clamp(0,1)
    # Double-angle dot product is invariant under edge polarity/180 degree flips.
    # Aligning gradient axes also aligns their perpendicular texture tangents.
    return ((1-(u*a+v*b).clamp(-1,1))*reliability).sum()/reliability.sum().clamp_min(1e-6)
