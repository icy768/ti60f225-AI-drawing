"""Fresh asymmetric three-expert network. No inherited local network or weights.

Only Conv2d (including depthwise/directional), ReLU6, add, concat, nearest resize,
and final clamp. No runtime image-wide normalization/statistics or attention.
"""
import torch
from torch import nn
from torch.ao.quantization import QuantStub, DeQuantStub
from torch.ao.nn.quantized import FloatFunctional

STYLES = ('vangogh', 'ukiyoe', 'ink')

class Conv(nn.Module):
    def __init__(self, a, b, k=3, s=1, groups=1, activation=True):
        super().__init__()
        pad=k//2 if isinstance(k,int) else (k[0]//2,k[1]//2)
        self.conv=nn.Conv2d(a,b,k,s,pad,groups=groups)
        self.act=nn.ReLU6() if activation else nn.Identity()
    def forward(self,x):return self.act(self.conv(x))

class Sep(nn.Module):
    def __init__(self,a,b,k=3,s=1):
        super().__init__();self.dw=Conv(a,a,k,s,groups=a);self.pw=Conv(a,b,1)
    def forward(self,x):return self.pw(self.dw(x))

class DirectionBlock(nn.Module):
    def __init__(self,c,hidden,k):
        super().__init__()
        self.expand=Conv(c,hidden,1)
        self.horizontal=Conv(hidden,hidden,(1,k),groups=hidden)
        self.vertical=Conv(hidden,hidden,(k,1),groups=hidden)
        self.local=Conv(hidden,hidden,3,groups=hidden)
        self.mix=Conv(hidden*3,c,1,activation=False)
        self.cat=FloatFunctional();self.add=FloatFunctional();self.act=nn.ReLU6()
    def forward(self,x):
        z=self.expand(x)
        y=self.cat.cat([self.horizontal(z),self.vertical(z),self.local(z)],1)
        return self.act(self.add.add(x,self.mix(y)))

class Expert(nn.Module):
    def __init__(self,hidden,kernels):
        super().__init__()
        self.spatial=Conv(64,64,3)
        self.blocks=nn.Sequential(*[DirectionBlock(64,hidden,k) for k in kernels])
        self.up4=nn.Upsample(scale_factor=2.,mode='nearest');self.up2=nn.Upsample(scale_factor=2.,mode='nearest');self.up1=nn.Upsample(scale_factor=2.,mode='nearest')
        self.decode4=Sep(64,32,5);self.skip4=Conv(40,32,1);self.add4=FloatFunctional()
        self.refine4=DirectionBlock(32,16,5)
        self.decode2=Sep(32,16,3);self.skip2=Conv(24,16,1);self.add2=FloatFunctional()
        self.refine2=Sep(16,16,5)
        self.decode1=Sep(16,8,3);self.skip1=Conv(8,8,3);self.add1=FloatFunctional()
        self.out=Conv(8,3,3,activation=False);self.clip=nn.Hardtanh(0.,1.)
    def forward(self,h,s4,s2,s1):
        h=self.blocks(self.spatial(h))
        h=self.refine4(self.add4.add(self.decode4(self.up4(h)),self.skip4(s4)))
        h=self.refine2(self.add2.add(self.decode2(self.up2(h)),self.skip2(s2)))
        h=self.add1.add(self.decode1(self.up1(h)),self.skip1(s1))
        return self.clip(self.out(h))

class TriStyle(nn.Module):
    def __init__(self):
        super().__init__()
        self.quant=QuantStub();self.dequant=DeQuantStub()
        self.stem=Conv(3,8,3)
        self.down2=Sep(8,24,3,2);self.down4=Sep(24,40,3,2);self.down8=Sep(40,64,3,2)
        # Different parameter banks, spatial kernels, residual blocks and output heads.
        self.experts=nn.ModuleList([
            Expert(88,[7,5,7,3]),
            Expert(72,[5,3,5,3]),
            Expert(80,[7,5,3,7]),
        ])
        self.reset_parameters()
    def reset_parameters(self):
        for m in self.modules():
            if isinstance(m,nn.Conv2d):
                nn.init.kaiming_normal_(m.weight,nonlinearity='relu')
                if m.bias is not None:nn.init.zeros_(m.bias)
        # Small residual paths keep initial activations within useful quantized range.
        for m in self.modules():
            if isinstance(m,DirectionBlock):
                nn.init.normal_(m.mix.conv.weight,0.,0.004)
        for e in self.experts:
            nn.init.normal_(e.out.conv.weight,0.,0.015)
            nn.init.constant_(e.out.conv.bias,0.5)
    def forward(self,x:torch.Tensor,style:int=0)->torch.Tensor:
        x=self.quant(x);s1=self.stem(x);s2=self.down2(s1);s4=self.down4(s2);h=self.down8(s4)
        # Enumerated ModuleList is compatible with TorchScript's runtime style index.
        for i,e in enumerate(self.experts):
            if i==style:return self.dequant(e(h,s4,s2,s1))
        raise RuntimeError('style must be 0, 1 or 2')

def parameter_report():
    m=TriStyle();rows={}
    for name,mod in [('shared',nn.ModuleList([m.stem,m.down2,m.down4,m.down8]))]+[(STYLES[i],e) for i,e in enumerate(m.experts)]:
        rows[name]={'parameters':sum(p.numel() for p in mod.parameters()),'weight_int8_bytes':sum(p.numel() for n,p in mod.named_parameters() if n.endswith('weight')),'bias_int32_bytes':4*sum(p.numel() for n,p in mod.named_parameters() if n.endswith('bias'))}
    return rows
if __name__=='__main__':
    import json
    print(json.dumps(parameter_report(),indent=2))
    m=TriStyle().eval()
    for s in range(3):print(s,m(torch.rand(1,3,64,80),s).shape)
