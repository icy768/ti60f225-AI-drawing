"""Optimize TRAINING pixels to distinguish a weak objective from a weak network.

These are diagnostic teacher-like optimizations, explicitly not student output
and never V4 promotion evidence. No holdout is optimized.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import sys
import time

import numpy as np
from PIL import Image, ImageDraw
import torch
from torch.nn import functional as F

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'experiments'))
sys.path.insert(0, str(ROOT / 'diagnostics'))
from v3_access import old, STYLES
from style_pilot import ContentMask, standardized, flow_continuity
from art_distribution import ArtDistribution
from distribution_objective import content_view, objective


def array(x):
    return (x.detach().cpu()[0].permute(1, 2, 0).clamp(0, 1).numpy() * 255).round().astype(np.uint8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--steps', type=int, default=240)
    ap.add_argument('--run', default='distribution_reachability_01')
    ap.add_argument('--style-specific', action='store_true')
    ap.add_argument('--ink-density', action='store_true')
    args = ap.parse_args()
    out = ROOT / 'reports' / args.run
    out.mkdir(exist_ok=False)
    source = out / 'source'
    source.mkdir()
    for p in [Path(__file__), ROOT / 'experiments/art_distribution.py', ROOT / 'experiments/distribution_objective.py', ROOT / 'data/stratified_art.py',
              ROOT / 'experiments/style_pilot.py', ROOT / 'diagnostics/v3_access.py']:
        (source / p.name).write_bytes(p.read_bytes())
    torch.set_num_threads(3)
    torch.manual_seed(20261020)
    random.seed(20261020)
    np.random.seed(20261020)
    dev = 'cuda'
    vgg = old.VGG().to(dev).eval()
    assert not args.ink_density or args.style_specific
    bank_path = ROOT / 'data' / ('realart_distribution_bank_v3.pt' if args.ink_density else 'realart_distribution_bank_v2.pt' if args.style_specific else 'realart_distribution_bank_v1.pt')
    bank = ArtDistribution(vgg, dev, bank_path, normalize_ink=args.style_specific, include_luminance=args.ink_density)
    ds = ContentMask()
    # A deterministic selection from training only, with ordinary subjects.
    indices = [8, 29, 47]
    data = [ds[i] for i in indices]
    x = torch.stack([z[0] for z in data]).to(dev)
    mask = torch.stack([z[1] for z in data]).to(dev)
    with torch.no_grad(), torch.autocast('cuda'):
        fx = vgg(x)
    rows = []
    started = time.time()
    for si, style in enumerate(STYLES):
        if args.style_specific:
            with torch.no_grad(), torch.autocast('cuda'):
                fx = vgg(content_view(x, style))
        y = torch.nn.Parameter(x.clone())
        opt = torch.optim.Adam([y], .015, betas=(.9, .99))
        log = []
        for step in range(args.steps + 1):
            opt.zero_grad(set_to_none=True)
            with torch.autocast('cuda'):
                fy = vgg(y)
                terms = bank.loss(fy, style)
                content = sum(F.l1_loss(standardized(fy[j]), standardized(fx[j])) for j in (2, 3))
                semantic = y.new_zeros(())
                for j in (2, 3):
                    mm = F.interpolate(mask, size=fy[j].shape[-2:], mode='area')
                    semantic += ((standardized(fy[j]) - standardized(fx[j])).abs() * mm).sum() / (mm.sum() * fy[j].shape[1] + 1e-5)
                weighted = {**terms, 'content': content * .1, 'semantic': semantic * .08}
                if si == 0:
                    # Weak directional regularizer, not an edge sharpening target.
                    weighted['flow'] = flow_continuity(y, x) * .25
                elif si == 2:
                    lum = (y * y.new_tensor([.299, .587, .114]).view(1, 3, 1, 1)).sum(1, keepdim=True)
                    weighted['ink_chroma'] = (y - lum).abs().mean() * .2
                loss = sum(weighted.values())
                if args.style_specific:
                    weighted = objective(y, x, mask, fy, fx, bank, style)
                    loss = sum(weighted.values())
            if not torch.isfinite(loss):
                raise FloatingPointError(f'Nonfinite diagnostic loss: {style}, step {step}')
            if step in (0, 1, 40, args.steps):
                grads = {}
                for name, term in weighted.items():
                    g = torch.autograd.grad(term, y, retain_graph=True)[0]
                    if not torch.isfinite(g).all():
                        raise FloatingPointError(f'Nonfinite diagnostic gradient: {style}, {name}, step {step}')
                    grads[name] = float(g.float().norm())
                row = {'step': step, 'style': style, 'terms': {k: float(v.detach()) for k, v in weighted.items()},
                       'output_gradient_L2': grads, 'input_MAE': float((y.detach() - x).abs().mean())}
                log.append(row)
                print('REACHABILITY', json.dumps(row), flush=True)
            if step == args.steps:
                break
            loss.backward()
            opt.step()
            with torch.no_grad():
                y.clamp_(0, 1)
        for k, i in enumerate(indices):
            im = Image.fromarray(array(y[k:k+1]))
            im.save(out / f'{ds.files[i].stem}_{style}_PIXEL_OPTIMIZATION_NOT_STUDENT.png')
        rows += log
    for k, i in enumerate(indices):
        Image.fromarray(array(x[k:k+1])).save(out / f'{ds.files[i].stem}_INPUT_TRAINING.png')
    sheet = Image.new('RGB', (256 * 4, (256 + 36) * len(indices)), 'white')
    d = ImageDraw.Draw(sheet)
    for row, i in enumerate(indices):
        names = [f'{ds.files[i].stem}_INPUT_TRAINING.png'] + [f'{ds.files[i].stem}_{s}_PIXEL_OPTIMIZATION_NOT_STUDENT.png' for s in STYLES]
        for col, name in enumerate(names):
            sheet.paste(Image.open(out / name), (256 * col, 292 * row))
            d.text((256 * col + 2, 292 * row + 257), (['TRAINING INPUT'] + list(STYLES))[col], fill='black')
    sheet.save(out / 'DIAGNOSTIC_PIXELS_NOT_STUDENT.jpg', quality=95)
    (out / 'result.json').write_text(json.dumps({'kind': 'TRAINING-pixel optimization diagnostic; NOT a trained student or promotion evidence',
          'steps_per_style': args.steps, 'training_inputs': [str(ds.files[i]) for i in indices], 'rows': rows,
          'seconds': time.time() - started, 'style_specific': args.style_specific, 'ink_density': args.ink_density,
          'bank_sha256': hashlib.sha256(bank_path.read_bytes()).hexdigest(),
          'promoted': False}, indent=2))
    print('REACHABILITY_FINISHED_NOT_STUDENT', flush=True)


if __name__ == '__main__':
    main()
