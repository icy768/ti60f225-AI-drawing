"""Perceptual, local patch, directional/region losses. Teachers never mix weights."""
import torch
from torch import nn
from torch.nn import functional as F
from torchvision.models import vgg16
class Perceptual(nn.Module):
    def __init__(self,path):
        super().__init__()
        net=vgg16(weights=None);sd=torch.load(path,map_location='cpu',weights_only=True);net.load_state_dict(sd)
        self.features=net.features[:23].eval()
        for p in self.features.parameters():p.requires_grad_(False)
        self.register_buffer('mean',torch.tensor([.485,.456,.406]).view(1,3,1,1));self.register_buffer('std',torch.tensor([.229,.224,.225]).view(1,3,1,1))
    def forward(self,x):
        x=(x-self.mean)/self.std;out=[]
        for i,m in enumerate(self.features):
            x=m(x)
            if i in [3,8,15,22]:out.append(x)
        return out
def feature_norm(x):
    return (x-x.mean((2,3),keepdim=True))/(x.std((2,3),keepdim=True)+.1)
def moment_loss(a,b):
    return F.l1_loss(a.mean((2,3)),b.mean((2,3)).expand(a.size(0),-1))+F.l1_loss(a.std((2,3)),b.std((2,3)).expand(a.size(0),-1))
def patch_loss(a,b,max_patches=256):
    # Local feature patch matching, preserving spatial neighborhoods; no global Gram.
    a=F.avg_pool2d(a,2);b=F.avg_pool2d(b,2)
    pa=F.unfold(a,3,padding=1).transpose(1,2);pb=F.unfold(b,3,padding=1).transpose(1,2)
    ids=torch.randperm(pa.size(1),device=a.device)[:max_patches];pa=pa[:,ids]
    ids=torch.randperm(pb.size(1),device=b.device)[:max_patches*2];pb=pb[:,ids].reshape(-1,pb.size(-1))
    na=F.normalize(pa,dim=-1);nb=F.normalize(pb,dim=-1)
    with torch.no_grad():idx=(na.detach()@nb.t()).argmax(-1)
    target=pb[idx]
    return F.l1_loss(pa,target)

def local_covariance_loss(a,b):
    # Covariance in 4x4 spatial windows, never one global Gram matrix.
    # Channel normalization keeps the term comparable across VGG stages.
    def stats(z):
        z=F.adaptive_avg_pool2d(z,(16,16))
        n,c,_,_=z.shape
        z=z.reshape(n,c,4,4,4,4).permute(0,2,4,1,3,5).reshape(-1,c,16)
        return torch.bmm(z,z.transpose(1,2))/(c*16)
    sa,sb=stats(a),stats(b)
    # Windows need not occupy the same semantic position in unpaired artwork.
    return F.l1_loss(sa.mean(0),sb.mean(0))

def teacher_texture(y,t):
    loss=y.new_zeros(())
    for k in [1,2,4]:
        a=F.avg_pool2d(y,k);b=F.avg_pool2d(t,k)
        # Remove low frequency color: teach marks/edges separately from palette.
        loss=loss+F.l1_loss(a-F.avg_pool2d(a,7,1,3),b-F.avg_pool2d(b,7,1,3))
        dy,dx=gradients(a);ty,tx=gradients(b)
        loss=loss+.5*(F.l1_loss(dx,tx)+F.l1_loss(dy,ty))
    return loss
def gray(x):return (x*torch.tensor([.299,.587,.114],device=x.device).view(1,3,1,1)).sum(1,keepdim=True)
def gradients(x):
    x=gray(x);return x[:,:,1:,:-1]-x[:,:,:-1,:-1],x[:,:,:-1,1:]-x[:,:,:-1,:-1]
def tensor_field(x):
    dy,dx=gradients(x);return F.avg_pool2d(torch.cat([dx*dx,dy*dy,dx*dy],1),7,1,3)
def edge_content(y,x):
    # Compare only coarse normalized structure, permit style-specific fine strokes.
    a,b=gradients(F.avg_pool2d(y,4)),gradients(F.avg_pool2d(x,4))
    return sum(F.l1_loss(u/(u.abs().mean((2,3),keepdim=True)+.03),v/(v.abs().mean((2,3),keepdim=True)+.03)) for u,v in zip(a,b))
def local_corr(x):
    x=gray(x);x=x-F.avg_pool2d(x,9,1,4)
    rows=[]
    for k in [1,2,4,8]:
        for dy,dx in [(0,k),(k,0),(k,k),(k,-k)]:
            a=x[:,:,:-k,:-k];b=x[:,:,dy:dy+a.size(2),dx:dx+a.size(3)] if dx>=0 else x[:,:,dy:dy+a.size(2),:a.size(3)]
            if dx<0:a=x[:,:,:-k,k:]
            rows.append((a*b).mean((2,3)))
    return torch.cat(rows,1)
def style_spatial(y,ref,style,x):
    loss=F.l1_loss(local_corr(y),local_corr(ref).mean(0,keepdim=True).expand(y.size(0),-1))*4.
    if style==0:
        # Match multiscale directional energies, avoid any imposed stripe/spiral template.
        for k in [1,2,4]:
            a=tensor_field(F.avg_pool2d(y,k));b=tensor_field(F.avg_pool2d(ref,k))
            loss=loss+moment_loss(a,b)*2.
    elif style==1:
        # Flat interiors only where original image is smooth; keep meaningful edges.
        dx,dy=gradients(y);cx,cy=gradients(x)
        smooth=torch.exp(-30*(cx.abs()+cy.abs()))
        loss=loss+((dx.abs()+dy.abs())*smooth).mean()*.25
        loss=loss+moment_loss(F.avg_pool2d(y,8),F.avg_pool2d(ref,8))*.25
    else:
        # Ink distribution and multiscale wash, no threshold whitening or grayscale output rule.
        for k in [1,4,16]:loss=loss+moment_loss(gray(F.avg_pool2d(y,k)),gray(F.avg_pool2d(ref,k)))
        loss=loss+(y.std(1).mean()-ref.std(1).mean()).abs()*.5
    return loss
class PatchDiscriminator(nn.Module):
    def __init__(self):
        super().__init__();self.net=nn.Sequential(nn.Conv2d(3,32,4,2,1),nn.LeakyReLU(.2),nn.Conv2d(32,64,4,2,1),nn.LeakyReLU(.2),nn.Conv2d(64,96,4,2,1),nn.LeakyReLU(.2),nn.Conv2d(96,1,3,1,1))
    def forward(self,x):return self.net(x)
