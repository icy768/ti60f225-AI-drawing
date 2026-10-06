"""Offline training supervision inspired by material construction; no inference ops.

This is new project code, not an implementation of the upstream generative skills.
No text, artificial border, screen-fixed noise, or semantic hallucination is added.
"""
import torch
import torch.nn.functional as F
from art_spatial_priors import mean, luma, contours

PALETTE = [[.10,.17,.24], [.16,.34,.49], [.36,.55,.65], [.70,.78,.78],
           [.96,.91,.79], [.78,.37,.25], [.43,.53,.34], [.79,.65,.43],
           [.60,.48,.36], [.90,.76,.58]]


def woodblock_palette_loss(y, source):
    colors=y.new_tensor(PALETTE)[None,:,:,None,None]
    distance=(y[:,None]-colors).square().sum(2).amin(1,keepdim=True)
    interior=(1-contours(guided(source))/.05).clamp(0,1).detach()
    return (distance*interior).sum()/interior.sum().clamp_min(1)


def guided(x, radius=5, eps=.018):
    g=luma(x); mg=mean(g,radius); mx=mean(x,radius)
    var=(mean(g*g,radius)-mg*mg).clamp_min(0)
    a=(mean(g*x,radius)-mg*mx)/(var+eps)
    return (mean(a,radius)*g+mean(mx-a*mg,radius)).clamp(0,1)


@torch.no_grad()
def material_target(x, style):
    z=guided(guided(x)); ed=contours(z)
    if style==1:
        # Lift broad shadow areas before matching to pigment blocks. Preserve
        # source chromatic differences instead of globally imposing blue/yellow.
        g=luma(z); lifted=(z+(g.pow(.68)-g)*.8).clamp(0,1)
        p=x.new_tensor(PALETTE)[None,:,:,None,None]
        delta=lifted[:,None]-p
        dl=.299*delta[:,:,0]+.587*delta[:,:,1]+.114*delta[:,:,2]
        distance=delta.square().sum(2)+2*dl.square()
        idx=distance.argmin(1)
        flat=x.new_tensor(PALETTE)[idx].permute(0,3,1,2)
        # Overlay ink on selected structural boundaries; do not multiply every
        # dark block towards zero as the v6 target did.
        line=((ed-.030)/.095).clamp(0,1)*.85
        ink=x.new_tensor([.10,.14,.18])[None,:,None,None]
        return flat*(1-line)+ink*line
    if style==2:
        g=luma(z)
        # Ink allocation follows existing tone and structure, without a fixed
        # central subject mask or new horizontal canvas.
        wash=.10+.24*torch.sigmoid((g-.11)*20)+.31*torch.sigmoid((g-.25)*18)+.35*torch.sigmoid((g-.42)*16)
        quiet=(1-ed/.045).clamp(0,1)
        # Pilot exposed over-lifting of dark subjects. Preserve dark washes;
        # mainly lift quiet midtones/highlights. Avoid targeting uniform pale
        # grey for the entire scene.
        lift_gate=torch.sigmoid((g-.26)*16)
        wash=wash+(.98-wash).clamp_min(0)*quiet*.32*lift_gate
        line=((ed-.025)/.105).clamp(0,1)
        density=1-wash
        density=1-(1-density)*(1-line*.78)
        # Modest dry variation only on source structural detail. No random
        # pattern or translated cartoon landscape is inserted.
        detail=(luma(x)-luma(guided(x,2,.008))).clamp(-.12,.12)
        density=(density-detail*.18*(ed/.04).clamp(0,1)).clamp(0,1)
        paper=x.new_tensor([.985,.977,.954])[None,:,None,None]
        ink=x.new_tensor([.085,.085,.080])[None,:,None,None]
        return paper*(1-density)+ink*density
    raise ValueError('No procedural Van Gogh teacher: use original artwork patches')


def patches(feature, max_count):
    # At relu2_2, average-pooling by two makes each 3x3 patch span 24 input
    # pixels. This couples neighbouring paint marks beyond single Gram entries.
    f=F.avg_pool2d(feature,2)
    p=F.unfold(f,3,padding=0).transpose(1,2).reshape(-1,feature.shape[1]*9)
    if len(p)>max_count:
        p=p[torch.linspace(0,len(p)-1,max_count,device=p.device).long()]
    return p


class PatchBank:
    def __init__(self, features):
        # Keep each artwork's patches separate in the dictionary; averaging
        # reference pixels/patches would blur the very marks being learned.
        self.raw=torch.cat([patches(f[1],256) for f in features]).detach()
        self.normal=F.normalize(self.raw,dim=1)
        self.energy=self.raw.square().mean().clamp_min(1e-6)

    def loss(self, feature):
        q=patches(feature,256)
        with torch.no_grad():
            match=(F.normalize(q.detach(),dim=1)@self.normal.T).argmax(1)
        return F.mse_loss(q,self.raw[match])/self.energy


def shift_consistency(net,x,style,reference,step):
    dx,dy=[(1,2),(4,-4),(-2,1),(8,0)][(step//4)%4]
    pad=12
    shifted=F.pad(x,(pad,)*4,mode='reflect')[:,:,pad+dy:pad+dy+x.shape[2],pad+dx:pad+dx+x.shape[3]]
    result=net(shifted,style)
    margin=28
    # Exclude receptive-field boundary effects. This is a translation proxy,
    # not a substitute for optical-flow/video evaluation.
    h,w=x.shape[-2:]
    return F.l1_loss(result[:,:,margin:h-margin,margin:w-margin],
                     reference.detach()[:,:,margin+dy:h-margin+dy,margin+dx:w-margin+dx])
