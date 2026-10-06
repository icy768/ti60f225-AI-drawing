"""Paired VGA evaluation of an integer candidate against its FP32 art target."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
import torch

import golden
from eval_art_region_v10 import inspect
from pc_validate import metric
from tinystyle import QCfg, TinyStyleNet
from train import ROOT


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--teacher', required=True)
    p.add_argument('--candidate', required=True)
    p.add_argument('--qparams', required=True)
    p.add_argument('--images', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--count', type=int, default=8)
    a = p.parse_args()
    root = Path(ROOT)
    out = root / a.out
    out.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(4)
    QCfg.enabled = QCfg.observe = False
    tc = torch.load(root / a.teacher, map_location='cpu', weights_only=False)
    cc = torch.load(root / a.candidate, map_location='cpu', weights_only=False)
    q = golden.load(str(root / a.qparams))
    if tc['cfg'] != cc['cfg'] or tc['styles'] != cc['styles'] or q['cfg'] != cc['cfg']:
        raise ValueError('Incompatible inference graph')
    nets = []
    for ck in (tc, cc):
        net = TinyStyleNet(**ck['cfg']).eval()
        net.load_state_dict(ck['sd'])
        nets.append(net.cuda())
    image_root = root / a.images
    records = []
    for j in range(a.count):
        image = image_root / f'{j:03}_input.png'
        source = np.asarray(Image.open(image).convert('RGB'))
        if source.shape != (480, 640, 3):
            raise ValueError(f'Unexpected image size: {image}')
        x = torch.from_numpy(source.copy()).permute(2, 0, 1)[None].cuda().float() / 255
        for si, style in enumerate(cc['styles']):
            st = torch.tensor([si], device='cuda')
            with torch.no_grad():
                tf = nets[0](x, st)
                cf = nets[1](x, st)
            def rgb(y):
                return (y[0].permute(1, 2, 0).cpu().numpy() * 255).round().clip(0, 255).astype(np.uint8)
            target, soft = rgb(tf), rgb(cf)
            hard, _, _ = golden.run(q, source, si)
            row = dict(image=image.name, style=style, integer_vs_v10_fp32=metric(hard, target),
                       integer_vs_own_fp32=metric(hard, soft),
                       own_fp32_vs_v10_fp32=metric(soft, target),
                       fp32_structure=inspect(source, soft, style),
                       integer_structure=inspect(source, hard, style))
            records.append(row)
            sheet = Image.new('RGB', (320 * 4, 270), 'white')
            draw = ImageDraw.Draw(sheet)
            for col, (label, arr) in enumerate(zip(('input', 'v10 FP32', 'v11 FP32', 'v11 integer'),
                                                   (source, target, soft, hard))):
                sheet.paste(Image.fromarray(arr).resize((320, 240)), (col * 320, 30))
                draw.text((col * 320 + 5, 7), label, fill='black')
            sheet.save(out / f'{style}_{j:03}.jpg', quality=95)
        print('EVAL', j + 1, '/', a.count, flush=True)
    means = {}
    for style in cc['styles']:
        subset = [r for r in records if r['style'] == style]
        means[style] = {key: {k: (None if all(r[key][k] is None for r in subset)
                                 else float(np.mean([r[key][k] for r in subset if r[key][k] is not None])))
                              for k in ('psnr', 'ssim', 'mae')}
                        for key in ('integer_vs_v10_fp32', 'integer_vs_own_fp32',
                                    'own_fp32_vs_v10_fp32')}
        means[style]['fp32_structure'] = {k: float(np.mean([r['fp32_structure'][k] for r in subset]))
                                          for k in subset[0]['fp32_structure']}
        means[style]['integer_structure'] = {k: float(np.mean([r['integer_structure'][k] for r in subset]))
                                             for k in subset[0]['integer_structure']}
    report = dict(protocol='identical eight held-out RGB VGA frames; rounded uint8 RGB; per-image arithmetic mean',
                  teacher_sha256=sha(root / a.teacher), candidate_sha256=sha(root / a.candidate),
                  qparams_json_sha256=sha(str(root / a.qparams) + '.json'),
                  image_sha256={f'{j:03}': sha(image_root / f'{j:03}_input.png') for j in range(a.count)},
                  means=means, records=records)
    (out / 'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(means, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
