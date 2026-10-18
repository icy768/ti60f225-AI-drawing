"""Review saved native student outputs. No training and no artistic pass score."""
import argparse
import hashlib
import html
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
STYLES = ('vangogh', 'ukiyoe', 'ink')


def load(path):
    return np.array(Image.open(path).convert('RGB'), copy=True)


def stats(a, x):
    a, x = a.astype(np.float32) / 255., x.astype(np.float32) / 255.
    g = cv2.cvtColor(a, cv2.COLOR_RGB2GRAY)
    gx = cv2.cvtColor(x, cv2.COLOR_RGB2GRAY)
    edge = lambda z: np.abs(np.diff(z, axis=0)).mean() + np.abs(np.diff(z, axis=1)).mean()
    return {'input_MAE_01': float(np.abs(a - x).mean()),
            'edge_energy_ratio_to_input': float(edge(g) / (edge(gx) + 1e-9)),
            'luminance_std': float(g.std()),
            'bright_pixel_fraction': float((g > .94).mean()),
            'near_gray_fraction': float((a.max(2) - a.min(2) < .035).mean())}


def panel(arrays, labels, title, crop=False):
    w, h = (256, 256) if crop else (384, 288)
    canvas = Image.new('RGB', (w * len(arrays), h + 48), 'white')
    draw = ImageDraw.Draw(canvas)
    for i, (a, label) in enumerate(zip(arrays, labels)):
        im = Image.fromarray(a)
        if crop:
            cx, cy = im.width // 2, im.height // 2
            im = im.crop((cx - 128, cy - 128, cx + 128, cy + 128))
        else:
            im.thumbnail((w, h), Image.Resampling.LANCZOS)
        canvas.paste(im, (i * w, 0))
        draw.text((i * w + 4, h + 3), label, fill='black')
    draw.text((4, h + 24), title, fill='black')
    return canvas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run', default='pilot_realart_v4_02')
    ap.add_argument('--step', type=int, default=2400)
    args = ap.parse_args()
    current = ROOT / 'reports' / args.run / f'{args.step:06d}'
    old = ROOT / 'reports' / 'pilot_realart_v4_01' / '002400'
    out = current / 'review'
    out.mkdir(exist_ok=True)
    inputs = json.loads((ROOT / 'data/fixed_test_manifest.json').read_text())
    rows, distances = [], []
    for name, entry in inputs.items():
        stem = Path(name).stem
        p = Path(entry['path'])
        assert hashlib.sha256(p.read_bytes()).hexdigest() == entry['sha256'], name
        x = load(p)
        ys = []
        for style in STYLES:
            v3 = load(current / f'{stem}_{style}_V3.png')
            v41 = load(old / f'{stem}_{style}_V4pilot.png')
            v42 = load(current / f'{stem}_{style}_V4pilot.png')
            assert x.shape == v3.shape == v41.shape == v42.shape
            ys.append(v42.astype(np.float32) / 255.)
            arrays = [x, v3, v41, v42]
            labels = ['INPUT', 'V3 frozen', 'V4 pilot 01', args.run]
            panel(arrays, labels, stem + ' / ' + style).save(out / f'{stem}_{style}_full.jpg', quality=94)
            panel(arrays, labels, stem + ' / ' + style + ' / native center crop', True).save(out / f'{stem}_{style}_crop.png')
            for label, a in zip(labels[1:], arrays[1:]):
                rows.append({'scene': stem, 'style': style, 'model': label, **stats(a, x)})
        distances.append({'scene': stem, 'pairs': {f'{STYLES[a]}_{STYLES[b]}': float(np.abs(ys[a] - ys[b]).mean())
                                                   for a, b in ((0, 1), (0, 2), (1, 2))}})
    means = {}
    for model in ('V3 frozen', 'V4 pilot 01', args.run):
        means[model] = {}
        for style in STYLES:
            selected = [r for r in rows if r['model'] == model and r['style'] == style]
            means[model][style] = {k: float(np.mean([r[k] for r in selected])) for k in selected[0] if k not in ('scene', 'style', 'model')}
    checkpoint = ROOT / 'experiments' / args.run / f'step_{args.step:06d}.pt'
    report = {'kind': 'Saved full-native-output diagnostics; NOT an artistic pass metric',
              'run': args.run, 'step': args.step, 'fixed_input_count': len(inputs),
              'checkpoint_sha256': hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
              'means': means, 'rows': rows, 'inter_style_MAE': distances,
              'promoted': False, 'visual_review': 'pending; full and center-crop panels generated'}
    (out / 'measurements.json').write_text(json.dumps(report, indent=2))
    stems = [Path(name).stem for name in inputs]
    for style in STYLES:
        for start in range(0, len(stems), 6):
            group = stems[start:start + 6]
            page = Image.new('RGB', (1024, 224 * len(group)), 'white')
            for row, stem in enumerate(group):
                tile = Image.open(out / f'{stem}_{style}_full.jpg').resize((1024, 224), Image.Resampling.LANCZOS)
                page.paste(tile, (0, row * 224))
            page.save(out / f'{style}_overview_{start // 6 + 1}.jpg', quality=94)
    body = ['<!doctype html><meta charset="utf-8"><title>V4 pilot actual student review</title>',
            '<style>body{font:16px sans-serif;max-width:1560px;margin:auto}img{max-width:100%}section{margin:3em 0}</style>',
            f'<h1>{html.escape(args.run)}: actual native student outputs</h1>',
            '<p>Exploratory pilot. No artistic promotion. INPUT / V3 frozen / failed pilot 01 / current pilot.</p>',
            '<p><a href="measurements.json">Measurements (not artistic scores)</a></p>']
    for style in STYLES:
        for stem in stems:
            body.append(f'<section><h2>{html.escape(style)} / {html.escape(stem)}</h2><img loading="lazy" src="{stem}_{style}_full.jpg"><p><a href="{stem}_{style}_crop.png">Native center crop</a></p></section>')
    (out / 'INDEX.html').write_text('\n'.join(body), encoding='utf-8')
    print(json.dumps({'means': means, 'checkpoint_sha256': report['checkpoint_sha256']}, indent=2))


if __name__ == '__main__':
    main()
