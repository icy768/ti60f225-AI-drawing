"""Independent image diagnostics and anonymized review sheets for v10."""
import argparse
import hashlib
import json
import random
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

from train import ROOT


STYLES = ('van_gogh', 'ukiyo_e', 'ink_landscape')


def gray(rgb):
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255


def gradient(x):
    return cv2.magnitude(cv2.Sobel(x, cv2.CV_32F, 1, 0, ksize=3) / 8,
                         cv2.Sobel(x, cv2.CV_32F, 0, 1, ksize=3) / 8)


def edge_f1(source, output):
    a = gradient(cv2.GaussianBlur(source, (0, 0), 1))
    b = gradient(cv2.GaussianBlur(output, (0, 0), 1))
    aa = a >= np.quantile(a, .90)
    bb = b >= np.quantile(b, .90)
    kernel = np.ones((5, 5), np.uint8)
    ad = cv2.dilate(aa.astype(np.uint8), kernel).astype(bool)
    bd = cv2.dilate(bb.astype(np.uint8), kernel).astype(bool)
    recall = float(np.mean(bd[aa])) if aa.any() else 0.0
    precision = float(np.mean(ad[bb])) if bb.any() else 0.0
    return dict(edge_recall=recall, edge_precision=precision,
                edge_f1=2 * recall * precision / max(recall + precision, 1e-8))


def inspect(source_rgb, output_rgb, style):
    source, output = gray(source_rgb), gray(output_rgb)
    edge = gradient(cv2.GaussianBlur(source, (0, 0), 1))
    quiet = edge < .025
    report = edge_f1(source, output)
    if style == 'van_gogh':
        broad = (edge < .035) & (source > .15) & (source < .85)
        highpass = np.abs(output - cv2.GaussianBlur(output, (0, 0), 2))
        report['surface_detail'] = float(highpass[broad].mean()) if broad.any() else 0.0
    elif style == 'ukiyo_e':
        dx = np.abs(np.diff(output, axis=1))[:-1]
        dy = np.abs(np.diff(output, axis=0))[:, :-1]
        core = quiet[:-1, :-1]
        report['flat_interior_fraction'] = float(np.mean(((dx < .01) & (dy < .01))[core])) if core.any() else 0.0
        report['mean_boundary_gradient'] = float(gradient(output)[edge >= .055].mean()) if (edge >= .055).any() else 0.0
    else:
        background = (source > .60) & quiet
        subject = source < .45
        report['background_paper_fraction'] = float(np.mean((output >= .90)[background])) if background.any() else 0.0
        report['subject_dark_fraction'] = float(np.mean((output <= .24)[subject])) if subject.any() else 0.0
        report['foreground_background_contrast'] = (float(output[background].mean() - output[subject].mean())
                                                   if background.any() and subject.any() else 0.0)
    return report


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--eval', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--models', nargs='+', required=True)
    p.add_argument('--count', type=int, default=8)
    args = p.parse_args()
    root = Path(ROOT)
    source = root / args.eval
    out = root / args.out
    out.mkdir(parents=True, exist_ok=False)
    rng = random.Random(20261004)
    records, keys = {}, {}
    for style in STYLES:
        records[style] = {}
        for model in args.models:
            rows = []
            for j in range(args.count):
                prefix = source / model
                original = np.asarray(Image.open(prefix / f'{j:03}_input.png').convert('RGB'))
                output = np.asarray(Image.open(prefix / f'{j:03}_{style}.png').convert('RGB'))
                rows.append(inspect(original, output, style))
            records[style][model] = {key: float(np.mean([row[key] for row in rows])) for key in rows[0]}
        for j in range(args.count):
            order = list(args.models)
            rng.shuffle(order)
            key = f'{style}_{j:03}'
            keys[key] = order
            sheet = Image.new('RGB', (320 * (len(order) + 1), 270), 'white')
            draw = ImageDraw.Draw(sheet)
            image = Image.open(source / order[0] / f'{j:03}_input.png').convert('RGB')
            sheet.paste(image.resize((320, 240)), (0, 30))
            draw.text((5, 8), f'{style} / input', fill='black')
            for i, model in enumerate(order, 1):
                image = Image.open(source / model / f'{j:03}_{style}.png').convert('RGB')
                sheet.paste(image.resize((320, 240)), (320 * i, 30))
                draw.text((320 * i + 5, 8), f'{style} / {chr(64 + i)}', fill='black')
            sheet.save(out / f'{key}.jpg', quality=96)
    (out / 'metrics.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
    (out / 'blind_key.json').write_text(json.dumps(keys, ensure_ascii=False, indent=2), encoding='utf-8')
    manifest = {'input_evaluation': str(source), 'models': args.models, 'count': args.count,
                'sheet_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.glob('*.jpg'))},
                'note': 'Sheets are anonymized for human review; metrics are diagnostics, not style scores.'}
    (out / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(records, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
