"""Render NEW train/validation guides only. Preview is explicitly TARGET, not student."""
import argparse, hashlib, json, pathlib, sys, time
import numpy as np
import cv2
from PIL import Image
ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / 'claude_impl'))
from train import save_grid
from painterly_guides import vangogh8, ukiyoe6, ink9, xdog
ap = argparse.ArgumentParser(); ap.add_argument('--split', choices=('train', 'validation'), default='validation')
ap.add_argument('--worker', type=int, default=0); ap.add_argument('--workers', type=int, default=1); ap.add_argument('--limit', type=int, default=0); ap.add_argument('--preview', action='store_true')
a = ap.parse_args(); cv2.setNumThreads(1)
denied = set(json.loads((ROOT / 'data/test/coco_test_ids.json').read_text())); rows = []; done = 0; t0 = time.time()
ann_path = ROOT / 'data/raw/instances_val2017.json'; ann = json.loads(ann_path.read_text(encoding='utf-8'))
sizes = {i['id']: (i['width'], i['height']) for i in ann['images']}; people = {}
for obj in ann['annotations']:
    if obj['category_id'] == 1: people.setdefault(obj['image_id'], []).append(obj['bbox'])
provenance = ROOT / 'data/claude_targets/painterly_p1_provenance'; provenance.mkdir(exist_ok=True)
source_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in [pathlib.Path(__file__), pathlib.Path(__file__).with_name('painterly_guides.py')]}
(provenance / f'{a.split}_{a.worker}_config.json').write_text(json.dumps({'args': vars(a), 'source': source_hashes,
    'annotation_sha256': hashlib.sha256(ann_path.read_bytes()).hexdigest(), 'depth': 'data/continuation_depth/config.json',
    'semantic_protection': 'training/validation COCO person-bbox upper head ellipse; narrow-band content detail and thin ink features only; mask NOT a student input'}, indent=2))
manifest = (provenance / f'{a.split}_{a.worker}_images.jsonl').open('a', buffering=1)
for i, p in enumerate(sorted((ROOT / 'data/claude_targets/content' / a.split).glob('*.png'))):
    if i % a.workers != a.worker: continue
    assert int(p.stem) not in denied
    depth = ROOT / 'data/continuation_depth' / a.split / (p.stem + '.npz')
    if not depth.exists():
        if a.preview: continue
        raise FileNotFoundError(depth)
    paths = [ROOT / 'data/claude_targets' / style / a.split / p.name for style in ('vangogh_p1', 'ukiyoe_p1', 'ink_p1')]
    rgb = np.array(Image.open(p).convert('RGB'), copy=True); near = np.load(depth)['near'].astype(np.float32)
    mask = np.zeros(rgb.shape[:2], np.float32); oh, ow = rgb.shape[:2]; origw, origh = sizes[int(p.stem)]
    for bx, by, bw, bh in people.get(int(p.stem), []):
        cx, cy = (bx + .5 * bw) * ow / origw, (by + .13 * bh) * oh / origh
        ax, ay = .38 * bw * ow / origw, .16 * bh * oh / origh
        if ay >= 5 and ax >= 5: cv2.ellipse(mask, (round(cx), round(cy)), (round(ax), round(ay)), 0, 0, 360, 1., -1)
    mask = cv2.GaussianBlur(mask, (0, 0), 1.5)
    mp = ROOT / 'data/claude_targets/content_masks' / a.split / p.name; mp.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray((mask * 255).round().astype(np.uint8)).save(mp)
    if not all(q.exists() for q in paths):
        h, w = near.shape; scale = min(1., 768 / max(h, w)); ww, hh = round(w * scale), round(h * scale)
        small_rgb, small_near = cv2.resize(rgb, (ww, hh)), cv2.resize(near, (ww, hh))
        for style_index, (q, fn) in enumerate(zip(paths, (vangogh8, ukiyoe6, ink9))):
            if q.exists(): continue
            y = fn(small_rgb, small_near)
            q.parent.mkdir(parents=True, exist_ok=True)
            y = cv2.resize(y, (w, h)); raw = rgb.astype(np.float32) / 255
            if style_index == 0:
                y = y + (raw - cv2.GaussianBlur(raw, (0, 0), .8)) * mask[..., None] * .45
            else:
                g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255
                fine = (1 - xdog(cv2.GaussianBlur(g, (0, 0), .35), sigma=.6, p=22, eps=.012, phi=9)) * mask * .50
                y = y * (1 - fine[..., None]) + np.array([.08, .085, .08]) * fine[..., None]
            Image.fromarray((y * 255).round().clip(0, 255).astype(np.uint8)).save(q)
    manifest.write(json.dumps({'stem': p.stem, 'content_sha256': hashlib.sha256(p.read_bytes()).hexdigest(),
        'depth_sha256': hashlib.sha256(depth.read_bytes()).hexdigest(), 'targets_sha256': {q.parent.parent.name: hashlib.sha256(q.read_bytes()).hexdigest() for q in paths},
        'mask_sha256': hashlib.sha256(mp.read_bytes()).hexdigest()}) + '\n')
    if a.preview: rows.append(('TARGET ' + p.stem, [rgb] + [np.array(Image.open(q)) for q in paths]))
    done += 1
    if done == 1 or done % 20 == 0: print(json.dumps({'split': a.split, 'worker': a.worker, 'done': done, 'elapsed': time.time() - t0}), flush=True)
    if a.limit and done >= a.limit: break
if a.preview:
    out = ROOT / 'reports/continuation/painterly_p1_TARGET_preview.jpg'; out.parent.mkdir(parents=True, exist_ok=True); save_grid(rows, out)
print('FINISHED', a.split, a.worker, done, time.time() - t0, flush=True)
