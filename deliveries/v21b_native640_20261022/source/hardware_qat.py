"""STE training with StyleCam's current-frame integer arithmetic in the forward pass.

R/S and activation scales are frozen by the deployment contract. This does not
simulate firmware refresh latency or CPU float32 table conversion.
"""
import torch
import torch.nn.functional as F


def forward(net, x, styles, contract):
    x=x+(torch.round(x.clamp(0,1)*255)/255-x).detach()
    feats=[]
    for i,(layer,L) in enumerate(zip(net.layers,contract["layers"])):
        soft=layer(x,styles,feats)
        with torch.no_grad():
            xi=torch.round(x.double()/L["s_x"])
            if L["up"]:xi=F.interpolate(xi,scale_factor=2,mode="nearest")
            w=layer.conv.weight.double()
            sw=w.abs().flatten(1).amax(1).clamp(min=1e-8)/127
            wq=torch.round(w/sw[:,None,None,None]).clamp(-127,127)
            # Integer sums are below 2**24 for this graph, so FP32 convolution
            # is exact when TF32 is disabled. Requant products use FP64.
            acc=F.conv2d(xi.float(),wq.float(),stride=L["stride"],padding=L["k"]//2,groups=L["groups"]).double()
            aa=torch.floor(acc/(2**L["R"])).clamp(-262144,262143)
            k=sw[None,:,None,None]*L["s_x"]
            if layer.norm is not None:
                mean=aa.mean((2,3),keepdim=True)
                var=(aa.square().mean((2,3),keepdim=True)-mean.square()).clamp(min=0)
                mu=mean*(2**L["R"])*k
                sig=torch.sqrt(var*(4**L["R"])*k.square()+layer.norm.eps)
                g=layer.norm.gamma[styles].double()[:,:,None,None]
                b=layer.norm.beta[styles].double()[:,:,None,None]
                mult=g*k/sig;add=b-g*mu/sig
            else:
                mult=k;add=layer.conv.bias.double()[None,:,None,None]
            m=torch.round(mult/L["s_y"]*(2**(L["S"]+L["R"]))).clamp(-131072,131071)
            bq=(torch.round(add/L["s_y"]*256)+128).clamp(-524288,524287)
            t=aa*m+bq*(2**(L["S"]-8))
            if L["skip"] is not None:
                skip=torch.round(feats[L["skip"]].double()/L["s_skip"])
                t+=skip*round(L["s_skip"]/L["s_y"]*(2**L["S"]))
            hard=torch.floor(t/(2**L["S"])).clamp(0,255)*L["s_y"]
        x=soft+(hard.to(soft.dtype)-soft).detach()
        feats.append(x)
    return F.pixel_shuffle(x,2)
