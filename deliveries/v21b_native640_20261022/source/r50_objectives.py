"""One new UK loss: differentiable attraction to ten original-reference colors."""
from pathlib import Path
import json
import torch
_palette=json.loads((Path(__file__).resolve().parents[1]/'R50/PALETTE.json').read_text(encoding='utf-8-sig'))
def palette_attraction(y):
    colors=torch.tensor(_palette['colors_rgb8'],device=y.device,dtype=y.dtype)/255
    d=(y[:,None,:,:,:]-colors[None,:,:,None,None]).square().mean(2)
    probability=torch.softmax(-d/_palette['temperature'],dim=1)
    return (probability*d).sum(1).mean()
