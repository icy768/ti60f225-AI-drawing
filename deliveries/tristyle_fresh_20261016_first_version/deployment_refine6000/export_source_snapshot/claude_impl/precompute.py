"""Precompute deterministic paired targets for train/validation (never test).
Images are resized so the short side is 320 px; stored as PNG under data/claude_targets/<style>/<split>/.
Usage: precompute.py <split> [worker_index n_workers] [--vg]
"""
import sys, json, pathlib, hashlib
import numpy as np
from PIL import Image
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from guides import ROOT, ukiyoe, ink
from guides2 import ukiyoe2, ink2

def load(p, short=320):
    im = Image.open(ROOT / p).convert('RGB'); r = short / min(im.size)
    im = im.resize((round(im.width * r) // 8 * 8, round(im.height * r) // 8 * 8), Image.Resampling.LANCZOS)
    return np.array(im)

def main():
    split = sys.argv[1]; vg = '--vg' in sys.argv
    args = [a for a in sys.argv[2:] if not a.startswith('--')]
    wi, nw = (int(args[0]), int(args[1])) if args else (0, 1)
    paths = json.loads((ROOT / 'data/splits.json').read_text())[split]
    test = set(json.loads((ROOT / 'data/test/coco_test_ids.json').read_text()))
    out = ROOT / 'data/claude_targets'
    if vg:
        from guides import VGTeacher
        t = VGTeacher()
    for i, p in enumerate(paths):
        if i % nw != wi: continue
        stem = pathlib.Path(p).stem; assert int(stem) not in test
        styles = ['content', 'vangogh'] if vg else (['ukiyoe2', 'ink2'] if '--v2' in sys.argv else ['ukiyoe', 'ink'])
        dst = {s: out / s / split / (stem + '.png') for s in styles}
        if all(d.exists() for d in dst.values()): continue
        rgb = load(p)
        for s, d in dst.items():
            d.parent.mkdir(parents=True, exist_ok=True)
            if s == 'content': y = rgb
            elif s == 'vangogh': y = (t(rgb) * 255).round().astype(np.uint8)
            elif s == 'ukiyoe': y = (ukiyoe(rgb, stem) * 255).round().astype(np.uint8)
            elif s == 'ink': y = (ink(rgb, stem) * 255).round().astype(np.uint8)
            elif s == 'ukiyoe2': y = (ukiyoe2(rgb, stem) * 255).round().astype(np.uint8)
            else: y = (ink2(rgb, stem) * 255).round().astype(np.uint8)
            Image.fromarray(y).save(d)
        if i % 50 == wi: print(split, i, len(paths), flush=True)
    print('done', split, wi, flush=True)

if __name__ == '__main__':
    main()
