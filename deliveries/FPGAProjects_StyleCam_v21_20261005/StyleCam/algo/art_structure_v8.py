"""Training-only structured supervision. No inference graph/postprocessor changes."""
import torch
import torch.nn.functional as F
from art_material_v7 import guided, material_target
from art_spatial_priors import mean, luma, contours


def gradient(x):
    return x[:,:,:,1:]-x[:,:,:,:-1], x[:,:,1:]-x[:,:,:-1]


def masked_l1(a,b,m):
    # Normalize within each sample and selected region: sparse ink lines must
    # not be overwhelmed by a much larger flat background.
    m=m.detach().expand_as(a)
    return (((a-b).abs()*m).flatten(1).sum(1)/m.flatten(1).sum(1).clamp_min(1)).mean()


@torch.no_grad()
def target(x,style):
    if style==1:
        base=material_target(x,1)
        # Use a wider spatially aligned line support than v7's sparse gradient
        # trace. Both sides of strong structural transitions can carry ink.
        ed=contours(guided(x,3,.008))
        line=((ed-.024)/.070).clamp(0,1)
        line=F.max_pool2d(line,3,1,1)*.85
        ink=x.new_tensor([.07,.09,.12])[None,:,None,None]
        return base*(1-line)+ink*line
    if style==2:
        g=luma(guided(x,3,.008)); e=contours(guided(x,3,.008))
        # Preserve dark wash before lifting quiet mid/high tones to paper.
        wash=.06+.25*torch.sigmoid((g-.17)*22)+.32*torch.sigmoid((g-.35)*20)+.37*torch.sigmoid((g-.54)*18)
        quiet=(1-e/.04).clamp(0,1)
        wash=wash+(1-wash)*quiet*torch.sigmoid((g-.45)*18)*.65
        line=((e-.025)/.08).clamp(0,1)*.82
        density=1-(wash*(1-line))
        # Source-bound dry detail only; no random marks or fixed white border.
        detail=(luma(x)-mean(luma(x),2)).clamp(-.08,.08)
        density=(density-.2*detail*(e/.04).clamp(0,1)).clamp(0,1)
        paper=x.new_tensor([.99,.982,.960])[None,:,None,None]
        ink=x.new_tensor([.045,.049,.052])[None,:,None,None]
        return paper*(1-density)+ink*density
    raise ValueError(style)


def separated_loss(y,t):
    e=contours(t); line=(e/.05).clamp(0,1)
    line=F.max_pool2d(line,3,1,1)
    interior=1-line
    pixels=.5*masked_l1(y,t,line)+.5*masked_l1(y,t,interior)
    # Signed RGB derivatives constrain position, contrast and hue boundaries,
    # unlike solely matching unsigned scalar edge energy.
    a,b=gradient(y);c,d=gradient(t)
    grad=.5*(masked_l1(a,c,line[:,:,:,1:])+masked_l1(b,d,line[:,:,1:]))
    tone=luma(t)
    dark=torch.sigmoid((.22-tone)*30)
    paper=torch.sigmoid((tone-.88)*30)
    tonal=.5*masked_l1(luma(y),tone,dark)+.5*masked_l1(luma(y),tone,paper)
    return pixels,grad,tonal


def spatial_covariance(f):
    """Local feature co-occurrence at 2/4 input pixels in relu1_2.

    No absolute screen coordinates or flow field are imposed. These descriptors
    are a texture aid, not evidence of semantic brush flow.
    """
    f=F.avg_pool2d(f,2); b,c,h,w=f.shape
    result=[]
    for dy,dx in [(0,1),(1,0),(1,1),(0,2),(2,0)]:
        a=f[:,:,:h-dy,:w-dx].flatten(2)
        z=f[:,:,dy:,dx:].flatten(2)
        result.append(torch.bmm(a,z.transpose(1,2))/(a.shape[-1]*c))
    return result


def covariance_loss(feature,targets):
    cov=spatial_covariance(feature)
    return sum(F.mse_loss(a,b.expand_as(a))/b.square().mean().clamp_min(1e-8) for a,b in zip(cov,targets))/len(cov)
