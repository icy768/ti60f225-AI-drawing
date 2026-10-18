"""TRAINING pixels only: can medium-scale real-art loss preserve subjects?

No network training or qualification. Two-scale pixel optimization with an
explicit multiscale residual parameterization, avoiding independent pixel noise
initialization. Saves actual intermediates and weighted output gradients.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import random
import sys
import time

import numpy as np
from PIL import Image, ImageDraw
import torch
from torch.nn import functional as F

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'experiments'))
sys.path.insert(0, str(ROOT/'diagnostics'))
from v3_access import old, STYLES, V3
from style_pilot import ContentMask
from relational_art import RelationalArt, gray, objective, random_grid


def array(x):
    return (x.detach().cpu().permute(1, 2, 0).clamp(0, 1).numpy()*255).round().astype(np.uint8)


def training_sample(ds, i, size):
    p = ds.files[i]
    im = Image.open(p).convert('RGB')
    mp = V3/'data/claude_targets/content_masks/train'/p.name
    mask = Image.open(mp).convert('L') if mp.exists() else Image.new('L', im.size, 0)
    assert im.size == mask.size, ('Misaligned source mask', p)
    original_size = list(im.size)
    scale = max(1., size/min(im.size))
    target = tuple(round(d*scale) for d in im.size)
    im = im.resize(target, Image.Resampling.LANCZOS)
    mask = mask.resize(target, Image.Resampling.NEAREST)
    left, top = random.randrange(im.width-size+1), random.randrange(im.height-size+1)
    box = (left, top, left+size, top+size)
    x = torch.from_numpy(np.array(im.crop(box), copy=True)).permute(2, 0, 1).float()/255.
    m = torch.from_numpy(np.array(mask.crop(box), copy=True))[None].float()/255.
    return x, m, {'path': str(p), 'source_size': original_size,
                  'resized_size': list(target), 'crop_box': list(box), 'mask_exists': mp.exists()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run', default='relational_reachability_01')
    ap.add_argument('--steps', type=int, default=180)
    args = ap.parse_args()
    out = ROOT/'reports'/args.run
    out.mkdir(exist_ok=False)
    seed = 20261027
    torch.set_num_threads(3)
    torch.manual_seed(seed); random.seed(seed); np.random.seed(seed)
    torch.backends.cudnn.benchmark = True
    sources = [Path(__file__), ROOT/'experiments/relational_art.py',
               ROOT/'experiments/style_pilot.py', ROOT/'data/stratified_art.py',
               ROOT/'diagnostics/v3_access.py']
    src = out/'source'; src.mkdir()
    for p in sources:
        (src/p.name).write_bytes(p.read_bytes())
    vgg = old.VGG().cuda().eval()
    cache = ROOT/'data/relational_realart_bank_v1.pt'
    bank = RelationalArt(vgg, 'cuda', cache)
    # Deterministic training-only selection distinct from the old three images.
    ds = ContentMask(size=384)
    ids = [17, 56, 91]
    samples = [training_sample(ds, i, 384) for i in ids]
    xfull = torch.stack([s[0] for s in samples]).cuda()
    mfull = torch.stack([s[1] for s in samples]).cuda()
    for k, i in enumerate(ids):
        Image.fromarray(array(xfull[k])).save(out/f'{ds.files[i].stem}_TRAINING_INPUT.png')
    cfg = {'time': datetime.datetime.now().astimezone().isoformat(), 'pid': os.getpid(),
           'kind': 'TRAINING pixel optimization diagnostic, NOT student/accepted teacher',
           'seed': seed, 'sizes': [192, 384], 'steps_per_size_style': args.steps,
           'training_inputs': [str(ds.files[i]) for i in ids],
           'training_input_transforms': [s[2] for s in samples],
           'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
           'reference_bank_sha256': hashlib.sha256(cache.read_bytes()).hexdigest(),
           'style_data': 'Corrected strict actual museum art; no StyleID/synthetic targets',
           'fixed17_used': False, 'heldout_video_used': False, 'promoted': False,
           'limitations': 'CUDA backward sampling may be nondeterministic; no claim of paper parity or network learnability'}
    (out/'config.json').write_text(json.dumps(cfg, indent=2))
    log = (out/'metrics.jsonl').open('w', buffering=1)
    started = time.time()
    for style in STYLES:
        prev = None
        for size in (192, 384):
            x = F.interpolate(xfull, size=(size, size), mode='area')
            mask = F.interpolate(mfull, size=(size, size), mode='area')
            view = gray(x).expand(-1, 3, -1, -1) if style == 'ink' else x
            with torch.no_grad(), torch.autocast('cuda'):
                fx = [z.detach() for z in vgg(view)]
            if prev is None:
                initial = x.clone()
            else:
                initial = F.interpolate(prev, size=(size, size), mode='bilinear', align_corners=False)
            # Optimize a low-frequency residual before full-size detail. Both
            # terms can change colors/regions without a prescribed paint target.
            coarse = torch.nn.Parameter(F.interpolate(initial, size=(size//4, size//4), mode='area'))
            fine = torch.nn.Parameter(initial-F.interpolate(coarse.detach(), size=(size, size), mode='bilinear', align_corners=False))
            opt = torch.optim.Adam([{'params': [coarse], 'lr': .018}, {'params': [fine], 'lr': .008}])
            for step in range(args.steps+1):
                opt.zero_grad(set_to_none=True)
                raw = F.interpolate(coarse, size=(size, size), mode='bilinear', align_corners=False)+fine
                y = raw+(raw.clamp(0, 1)-raw).detach()
                ag = random_grid(len(ids), 384, 'cuda')
                rg = random_grid(len(ids), 192, 'cuda')
                with torch.autocast('cuda'):
                    fy = vgg(y)
                    terms = objective(y, x, mask, fy, fx, bank, style, ag, rg)
                    loss = sum(terms.values())
                if not torch.isfinite(loss):
                    raise FloatingPointError((style, size, step))
                if step in (0, 1, 60, args.steps):
                    grads = {k: torch.autograd.grad(v, y, retain_graph=True)[0].float().detach()
                             for k, v in terms.items()}
                    ga, gc = grads['art_nearest'].flatten(), grads['content_relationships'].flatten()
                    row = {'style': style, 'size': size, 'step': step,
                           'weighted_terms': {k: float(v.detach()) for k, v in terms.items()},
                           'output_gradient_L2': {k: float(v.norm()) for k, v in grads.items()},
                           'art_relation_cosine': float(F.cosine_similarity(ga, gc, dim=0)),
                           'input_MAE': float((y-x).abs().mean()), 'seconds': time.time()-started}
                    log.write(json.dumps(row)+'\n'); print('RELATIONAL_DIAGNOSTIC', json.dumps(row), flush=True)
                if step in (60, args.steps):
                    for k, i in enumerate(ids):
                        Image.fromarray(array(y[k])).save(out/f'{ds.files[i].stem}_{style}_{size}_{step:04d}_PIXELS_NOT_STUDENT.png')
                if step == args.steps:
                    prev = y.detach()
                    break
                loss.backward()
                opt.step()
            del opt, fy, fx
    sheet = Image.new('RGB', (384*4, (384+26)*len(ids)), 'white')
    draw = ImageDraw.Draw(sheet)
    for row, i in enumerate(ids):
        names = [f'{ds.files[i].stem}_TRAINING_INPUT.png']+[
            f'{ds.files[i].stem}_{s}_384_{args.steps:04d}_PIXELS_NOT_STUDENT.png' for s in STYLES]
        for col, name in enumerate(names):
            sheet.paste(Image.open(out/name), (384*col, 410*row))
            label = 'TRAINING INPUT' if col == 0 else STYLES[col-1]+' PIXELS, NOT STUDENT'
            draw.text((384*col+3, 410*row+387), label, fill='black')
    sheet.save(out/'DIAGNOSTIC_NOT_STUDENT.jpg', quality=95)
    (out/'finished.json').write_text(json.dumps({'time': datetime.datetime.now().astimezone().isoformat(),
         'seconds': time.time()-started, 'promoted': False, 'quality': 'await actual visual review'}))
    print('RELATIONAL_REACHABILITY_FINISHED_NOT_STUDENT', flush=True)


if __name__ == '__main__':
    main()
