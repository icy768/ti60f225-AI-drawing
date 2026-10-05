"""Compare fixed-graph QAT checkpoints with style retention as the first gate.

PSNR/SSIM here measure fidelity to the v10 artistic output, not to the photo.
They are meaningful only together with the independent style diagnostics and
blind review sheets written by this script.
"""
import argparse
import hashlib
import json
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
import torch

import golden
from eval_art_region_v10 import inspect
from pc_validate import metric
from tinystyle import QCfg, TinyStyleNet
from train import ROOT


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rgb(y):
    return (y[0].permute(1, 2, 0).cpu().numpy() * 255).round().clip(0, 255).astype(np.uint8)


def mean_dict(rows):
    return {k: float(np.mean([r[k] for r in rows])) for k in rows[0]}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--teacher', required=True)
    p.add_argument('--contract', required=True)
    p.add_argument('--images', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--candidates', nargs='+', required=True)
    p.add_argument('--count', type=int, default=8)
    a = p.parse_args()
    root = Path(ROOT)
    out = root / a.out
    out.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(4)
    QCfg.enabled = QCfg.observe = False
    paths = [root / p for p in [a.teacher, *a.candidates]]
    checks = [torch.load(p, map_location='cpu', weights_only=False) for p in paths]
    contract = golden.load(str(root / a.contract))
    if len(set(map(str, [c['cfg'] for c in checks]))) != 1 or any(
            c['styles'] != checks[0]['styles'] for c in checks):
        raise ValueError('Inference graphs or styles differ')
    if checks[0]['cfg'] != contract['cfg'] or checks[0]['styles'] != contract['styles']:
        raise ValueError('Integer contract differs from candidate graph')
    nets = []
    for ck in checks:
        net = TinyStyleNet(**ck['cfg']).cuda().eval()
        net.load_state_dict(ck['sd'])
        nets.append(net)
    qmodels = []
    for path in paths[1:]:
        q = golden.export_float(str(path))
        for layer, frozen in zip(q['layers'], contract['layers']):
            if not np.isclose(layer['s_y'], frozen['s_y'], rtol=1e-6, atol=1e-10):
                raise ValueError('Activation scale changed: ' + layer['name'])
            layer['R'], layer['S'] = frozen['R'], frozen['S']
        qmodels.append(q)
    names = ['v10', *[f'candidate_{i}' for i in range(len(a.candidates))]]
    rows = {style: {name: [] for name in names} for style in checks[0]['styles']}
    blind_key = {}
    rng = random.Random(20261004)
    image_hashes = {}
    for j in range(a.count):
        image_path = root / a.images / f'{j:03}_input.png'
        source = np.asarray(Image.open(image_path).convert('RGB'))
        if source.shape != (480, 640, 3):
            raise ValueError(f'Expected RGB VGA: {image_path}')
        image_hashes[image_path.name] = digest(image_path)
        x = torch.from_numpy(source.copy()).permute(2, 0, 1)[None].cuda().float() / 255
        for si, style in enumerate(checks[0]['styles']):
            st = torch.tensor([si], device='cuda')
            with torch.no_grad():
                float_images = [rgb(net(x, st)) for net in nets]
            int_images = [golden.run(q, source, si)[0] for q in qmodels]
            target = float_images[0]
            rows[style]['v10'].append(dict(fp32_structure=inspect(source, target, style)))
            for i, (soft, hard) in enumerate(zip(float_images[1:], int_images)):
                rows[style][names[i + 1]].append(dict(
                    fp32_vs_v10=metric(soft, target),
                    integer_vs_v10=metric(hard, target),
                    integer_vs_own_fp32=metric(hard, soft),
                    fp32_structure=inspect(source, soft, style),
                    integer_structure=inspect(source, hard, style)))
            outputs = dict(zip(names, float_images))
            order = list(names)
            rng.shuffle(order)
            blind_key[f'{style}_{j:03}'] = order
            sheet = Image.new('RGB', (320 * (len(order) + 1), 270), 'white')
            draw = ImageDraw.Draw(sheet)
            sheet.paste(Image.fromarray(source).resize((320, 240)), (0, 30))
            draw.text((5, 7), 'input', fill='black')
            for col, name in enumerate(order, 1):
                sheet.paste(Image.fromarray(outputs[name]).resize((320, 240)), (col * 320, 30))
                draw.text((col * 320 + 5, 7), chr(64 + col), fill='black')
            sheet.save(out / f'blind_{style}_{j:03}.jpg', quality=95)
        print(f'EVAL {j + 1}/{a.count}', flush=True)
    summary = {}
    for style, models in rows.items():
        summary[style] = {'v10': {'fp32_structure': mean_dict([r['fp32_structure'] for r in models['v10']])}}
        for name in names[1:]:
            data = models[name]
            summary[style][name] = {field: mean_dict([r[field] for r in data]) for field in
                                    ('fp32_structure', 'integer_structure')}
            for field in ('fp32_vs_v10', 'integer_vs_v10', 'integer_vs_own_fp32'):
                summary[style][name][field] = {}
                for key in ('psnr', 'ssim', 'mae'):
                    values = [r[field][key] for r in data if r[field][key] is not None]
                    summary[style][name][field][key] = float(np.mean(values)) if values else None
    report = dict(protocol='same held-out RGB VGA images; uint8 RGB; mean per image; v10 FP32 artistic reference',
                  caveat='PSNR/SSIM are fidelity to v10 stylization, not a same-domain quality threshold',
                  teacher=a.teacher, candidates=a.candidates, paths_sha256={str(p): digest(p) for p in paths},
                  contract_json_sha256=digest(str(root / a.contract) + '.json'),
                  image_sha256=image_hashes, graph_unchanged=True, board_validated=False,
                  summary=summary, records=rows)
    (out / 'summary.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    (out / 'blind_key.json').write_text(json.dumps(blind_key, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == '__main__':
    main()
