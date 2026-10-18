"""Single TRAINING-crop fitting control, never quality/generalization evidence.

The saved pixel-optimization diagnostic is an imperfect fixed signal, not a
selected teacher. Holding input/target/loss/updates constant tests whether the
decoder can express that signal. No fixed17 or held-out video is optimized.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import random
import sys
import time

import numpy as np
from PIL import Image, ImageDraw
import torch
from torch import nn
from torch.nn import functional as F

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'experiments'))
from model_v4_replicate import ReplicateV4
from model_v4_subpixel import SubpixelV4
from model_v4_subpixel_lite import SubpixelLiteV4
from style_pilot_v4 import parameter_storage

STYLES = ('vangogh', 'ukiyoe', 'ink')


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load(p):
    a = np.array(Image.open(p).convert('RGB'), copy=True)
    return torch.from_numpy(a).permute(2, 0, 1)[None].float().cuda()/255


def image(x):
    return Image.fromarray((x.detach()[0].float().clamp(0, 1).permute(1, 2, 0).cpu().numpy()*255).round().astype(np.uint8))


def hp(x):
    return x - F.avg_pool2d(F.pad(x, (2, 2, 2, 2), mode='replicate'), 5, 1)


def metrics(y, target, source):
    a, b = hp(y).flatten(1), hp(target).flatten(1)
    a, b = a-a.mean(1, keepdim=True), b-b.mean(1, keepdim=True)
    return {'MAE': float((y-target).abs().mean()), 'PSNR_dB': float(-10*torch.log10((y-target).square().mean().clamp_min(1e-12))),
            'highpass_MAE': float((hp(y)-hp(target)).abs().mean()),
            'highpass_correlation': float(F.cosine_similarity(a, b, dim=1).mean()),
            'input_MAE': float((y-source).abs().mean()), 'clipped_fraction': float(((y<.001)|(y>.999)).float().mean())}


def macs(model, style):
    count = 0
    def hook(m, inp, out):
        nonlocal count
        count += out.numel()*m.weight[0].numel()
    hooks = [m.register_forward_hook(hook) for m in model.modules() if isinstance(m, nn.Conv2d)]
    with torch.no_grad():
        model(torch.zeros(1, 3, 480, 640, device='cuda'), style)
    for h in hooks:
        h.remove()
    return count


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run', default='decoder_capacity_01')
    ap.add_argument('--updates-per-style', type=int, default=900)
    ap.add_argument('--models', nargs='+', choices=('A64_replicate', 'subpixel', 'subpixel_lite'), default=['A64_replicate', 'subpixel'])
    args = ap.parse_args()
    out = ROOT/'reports'/args.run
    out.mkdir(exist_ok=False)
    torch.set_num_threads(3)
    torch.backends.cudnn.benchmark = True
    diag = ROOT/'reports/distribution_reachability_05'
    stem = '000000002153'
    paths = [diag/f'{stem}_INPUT_TRAINING.png']+[diag/f'{stem}_{s}_PIXEL_OPTIMIZATION_NOT_STUDENT.png' for s in STYLES]
    source, *targets = [load(p) for p in paths]
    cfg = {'kind': 'Single training-crop capacity diagnostic, NOT student quality or generalization evidence',
           'time': datetime.datetime.now().astimezone().isoformat(), 'updates_per_style': args.updates_per_style,
           'training_input': stem, 'fixed_target_policy': 'Imperfect pixel-optimization diagnostic, not accepted teacher. Same target for each model.',
           'loss': 'L1 + 2*5x5-highpass-L1; no realart/semantic/video loss in this capacity control',
           'seed': 20261023, 'optimizer': 'Adam lr=.0008, betas=.9,.99, gradclip3; shared/expert same rate',
           'input_target_sha256': {str(p.relative_to(ROOT)): sha(p) for p in paths},
           'source_sha256': {}, 'models': {}, 'promoted': False}
    for rel in ('diagnostics/decoder_capacity.py', 'experiments/model_v4_subpixel.py', 'experiments/model_v4_subpixel_lite.py',
                'experiments/model_v4_replicate.py', 'experiments/model_v4_stable.py',
                'experiments/model_v4_init_v2.py', 'experiments/model_v4_draft.py', 'experiments/style_pilot_v4.py'):
        p = ROOT/rel
        dest = out/'source'/rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(p.read_bytes())
        cfg['source_sha256'][rel] = sha(p)
    (out/'config.json').write_text(json.dumps(cfg, indent=2))
    log = (out/'metrics.jsonl').open('w', buffering=1)
    source_image = image(source)
    source_image.save(out/'INPUT_TRAINING.png')
    constructors = {'A64_replicate': lambda: ReplicateV4(detail_scale=.35, residual_scale=.65),
                    'subpixel': lambda: SubpixelV4(residual_scale=.65),
                    'subpixel_lite': lambda: SubpixelLiteV4(residual_scale=.65)}
    for name in args.models:
        constructor = constructors[name]
        torch.manual_seed(cfg['seed'])
        random.seed(cfg['seed'])
        np.random.seed(cfg['seed'])
        model = constructor().cuda()
        cost = {'VGA_conv_MAC': [macs(model, i) for i in range(3)], **parameter_storage(model),
                'actual_integer_export': False, 'actual_FPGA_resources': None, 'actual_board_FPS': None}
        cfg['models'][name] = cost
        (out/'config.json').write_text(json.dumps(cfg, indent=2))
        optimizer = torch.optim.Adam(model.parameters(), lr=8e-4, betas=(.9, .99))
        scaler = torch.amp.GradScaler('cuda', init_scale=1024)
        start = time.time()
        for step in range(1, args.updates_per_style*3+1):
            si = (step-1)%3
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast('cuda'):
                y = model(source, si)
                loss = (y-targets[si]).abs().mean()+2*(hp(y)-hp(targets[si])).abs().mean()
            if not torch.isfinite(loss):
                raise FloatingPointError((name, step, loss))
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            norm = torch.nn.utils.clip_grad_norm_(model.parameters(), 3, error_if_nonfinite=True)
            scaler.step(optimizer)
            scaler.update()
            if step in (1, 2, 3) or step%300 in (298, 299, 0):
                row = {'model': name, 'step': step, 'style': STYLES[si], 'loss': float(loss.detach()),
                       'gradnorm': float(norm), **metrics(y.detach().float(), targets[si], source), 'seconds': time.time()-start}
                log.write(json.dumps(row)+'\n')
                print('CAPACITY_DIAGNOSTIC', json.dumps(row), flush=True)
            if step%900 == 0 or step == args.updates_per_style*3:
                torch.save({'model': model.state_dict(), 'step': step, 'config': cfg,
                    'optimizer': optimizer.state_dict(), 'scaler': scaler.state_dict(),
                    'torch_rng': torch.get_rng_state(), 'cuda_rng': torch.cuda.get_rng_state_all(),
                    'python_rng': random.getstate(), 'numpy_rng': np.random.get_state()}, out/f'{name}_latest.pt')
        model.eval()
        results = {}
        with torch.no_grad():
            for si, style in enumerate(STYLES):
                y = model(source, si)
                results[style] = metrics(y, targets[si], source)
                image(y).save(out/f'{name}_{style}_SINGLE_TRAINING_CROP_FIT.png')
        (out/f'{name}_result.json').write_text(json.dumps({'cost': cost, 'fits': results,
            'seconds': time.time()-start, 'promoted': False}, indent=2))
        del model, optimizer, scaler
        torch.cuda.empty_cache()
    sheet = Image.new('RGB', ((2+len(args.models))*256, 3*286), 'white')
    draw = ImageDraw.Draw(sheet)
    for si, style in enumerate(STYLES):
        images = [source_image, image(targets[si])]+[Image.open(out/f'{m}_{style}_SINGLE_TRAINING_CROP_FIT.png') for m in args.models]
        labels = ['TRAIN INPUT', 'IMPERFECT DIAGNOSTIC TARGET']+[m+' SINGLE-CROP FIT' for m in args.models]
        for col, (im, label) in enumerate(zip(images, labels)):
            sheet.paste(im, (col*256, si*286))
            draw.text((col*256+2, si*286+257), style+' '+label, fill='black')
    sheet.save(out/'CAPACITY_ONLY_NOT_GENERALIZATION.jpg', quality=96)
    (out/'finished.json').write_text(json.dumps({'time': datetime.datetime.now().astimezone().isoformat(), 'promoted': False}))
    print('CAPACITY_DIAGNOSTIC_FINISHED_NO_PROMOTION', flush=True)


if __name__ == '__main__':
    main()
