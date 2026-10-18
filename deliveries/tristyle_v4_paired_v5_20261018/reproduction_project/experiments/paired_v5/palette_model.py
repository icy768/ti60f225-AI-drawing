"""PLAN §5.3 B-plan: 16 palette logits plus one contour logit, UK only.

Inference uses argmax, a 16x3 uint8 LUT and a threshold contour overlay. Training
uses a differentiable palette mixture, never a photograph reconstruction anchor.
"""
import sys
from pathlib import Path
import torch
from torch import nn
from torch.nn import functional as F
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'diagnostics'))
import v3_access
from model import Expert,CB

PALETTE=[[41,56,92],[51,92,143],[158,189,209],[204,219,219],
         [51,84,61],[102,140,82],[168,184,107],[199,153,77],
         [204,77,51],[237,204,168],[240,230,204],[31,28,31],
         [122,82,56],[140,140,133],[224,168,168],[224,204,158]]

class PaletteExpert(Expert):
    def forward(self,f1,f2,f4,f8):
        logits=super().forward(f1,f2,f4,f8)
        self.current_logits=logits
        palette=self.palette_rgb.float()/255
        if self.training:
            rgb=torch.einsum('bkhw,kc->bchw',logits[:,:16].softmax(1),palette)
            alpha=logits[:,16:17].sigmoid()
            return rgb*(1-alpha)+palette[0][None,:,None,None]*alpha
        labels=logits[:,:16].argmax(1)
        rgb=palette[labels].permute(0,3,1,2)
        return torch.where(logits[:,16:17]>0,palette[0][None,:,None,None],rgb)

def upgrade_palette(model,initialize_from_rgb=True):
    expert=model.experts[1]
    if isinstance(expert,PaletteExpert):return model
    old=expert.head.conv
    head=CB(old.in_channels,17,3,relu=False).to(old.weight.device)
    palette=torch.tensor(PALETTE,dtype=torch.float32,device=old.weight.device)/255
    if initialize_from_rgb:
        # Nearest-palette logits of the old RGB prediction: 2*p*x - ||p||^2.
        with torch.no_grad():
            head.conv.weight[:16].copy_(torch.einsum('kc,cihw->kihw',palette*20,old.weight))
            head.conv.bias[:16].copy_(20*palette@old.bias-10*(palette**2).sum(1))
            head.conv.weight[16].zero_();head.conv.bias[16]=-3
    expert.head=head;expert.__class__=PaletteExpert
    expert.register_buffer('palette_rgb',torch.tensor(PALETTE,dtype=torch.uint8,device=old.weight.device))
    return model

def model_for_state(state):
    model=v3_access.model_for_state(state)
    if state['experts.1.head.conv.weight'].shape[0]==17:upgrade_palette(model,False)
    return model

def paired_classification(model,target):
    logits=model.experts[1].current_logits
    palette=model.experts[1].palette_rgb.float()/255
    distances=((target[:,None]-palette[None,:,:,None,None])**2).sum(2)
    labels=distances.argmin(1)
    # Deep-indigo contour only where the registered teacher has a dark edge.
    lum=(target*target.new_tensor([.299,.587,.114])[None,:,None,None]).sum(1,keepdim=True)
    hi=F.max_pool2d(lum,3,1,1);lo=-F.max_pool2d(-lum,3,1,1)
    contour=((lum<.24)&((hi-lo)>.08)).float()
    return {'paired_palette_CE':F.cross_entropy(logits[:,:16],labels),
            'paired_contour_BCE':F.binary_cross_entropy_with_logits(logits[:,16:17],contour,pos_weight=logits.new_tensor(3.))*.5}
