"""Read-only trained-weight padding/resolution intervention; training inputs only."""
import json
import hashlib
from pathlib import Path
import random
import sys

import numpy as np
from PIL import Image, ImageDraw
import torch
from torch import nn
from torch.nn import functional as F

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'experiments'))
sys.path.insert(0, str(ROOT / 'diagnostics'))
from model_v4_stable import StableV4
from style_pilot import ContentMask


def array(y):
    return (y.detach()[0].permute(1, 2, 0).cpu().clamp(0, 1).numpy() * 255).round().astype(np.uint8)


def stats(y):
    g = y.mean(1)[0]
    h, w = g.shape
    center = g[h//4:3*h//4, w//4:3*w//4].mean()
    edge = torch.cat((g[:h//8].flatten(), g[-h//8:].flatten(), g[:, :w//8].flatten(), g[:, -w//8:].flatten())).mean()
    return {'mean': float(g.mean()), 'std': float(g.std()), 'center_minus_border': float(center-edge)}


def main():
    torch.set_num_threads(3)
    torch.manual_seed(20261021)
    random.seed(20261021)
    out = ROOT / 'reports/padding_diagnostic'
    out.mkdir(exist_ok=True)
    checkpoint = ROOT / 'experiments/pilot_distribution_v4_01/step_002400.pt'
    ck = torch.load(checkpoint, map_location='cuda', weights_only=False)
    m = StableV4(.35, .65).cuda().eval()
    m.load_state_dict(ck['model'])
    ds = ContentMask()
    real = ds[29][0][None].cuda()
    inputs = [(f'constant_{level}', torch.full((1, 3, 256, 256), level, device='cuda')) for level in (.25, .5, .75)]
    inputs.append(('TRAINING_' + ds.files[29].stem, real))
    rows = []
    modes = ('zeros', 'replicate', 'reflect')
    sizes = (256, 512)
    with torch.no_grad():
        for name, x in inputs:
            for si, style in enumerate(('vangogh', 'ukiyoe', 'ink')):
                sheet = Image.new('RGB', (256*6, 292), 'white')
                d = ImageDraw.Draw(sheet)
                for col, (mode, size) in enumerate((mo, sz) for mo in modes for sz in sizes):
                    for layer in m.modules():
                        if isinstance(layer, nn.Conv2d):
                            layer.padding_mode = mode
                    z = F.interpolate(x, size=(size, size), mode='bilinear', align_corners=False)
                    y = m(z, si)
                    im = Image.fromarray(array(y))
                    im.save(out / f'{name}_{style}_{mode}_{size}.png')
                    sheet.paste(im.resize((256, 256), Image.Resampling.LANCZOS), (col*256, 0))
                    d.text((col*256+2, 260), f'{mode} / {size} / TRAINING DIAG', fill='black')
                    rows.append({'input': name, 'style': style, 'padding': mode, 'size': size, **stats(y)})
                sheet.save(out / f'{name}_{style}_DIAGNOSTIC.jpg', quality=95)
    report = {'kind': 'Frozen student weights with inference-only padding/resolution intervention; NOT a trained replacement or artistic improvement evidence',
              'checkpoint_sha256': hashlib.sha256(checkpoint.read_bytes()).hexdigest(), 'rows': rows,
              'fixed17_optimized': False, 'promoted': False}
    (out / 'result.json').write_text(json.dumps(report, indent=2))
    print(json.dumps([r for r in rows if r['input'] == 'constant_0.5'], indent=2), flush=True)


if __name__ == '__main__':
    main()
