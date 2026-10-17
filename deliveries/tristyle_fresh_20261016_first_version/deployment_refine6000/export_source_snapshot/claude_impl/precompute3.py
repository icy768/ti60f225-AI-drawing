"""Deterministic v3 targets vangogh3 (needs existing data/claude_targets/vangogh AdaIN palette) and ink3.
Usage: precompute3.py <split> <worker> <n_workers>"""
import sys, json, pathlib, numpy as np
from PIL import Image
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from guides import ROOT
from guides3 import vangogh3, ink3
T = ROOT / 'data/claude_targets'
split, wi, nw = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
test = set(json.loads((ROOT / 'data/test/coco_test_ids.json').read_text()))
stems = sorted(p.stem for p in (T / 'content' / split).glob('*.png'))
for i, s in enumerate(stems):
    if i % nw != wi: continue
    assert int(s) not in test
    d1, d2 = T / 'vangogh3' / split / (s + '.png'), T / 'ink3' / split / (s + '.png')
    if d1.exists() and d2.exists(): continue
    rgb = np.array(Image.open(T / 'content' / split / (s + '.png')).convert('RGB')); v = np.array(Image.open(T / 'vangogh' / split / (s + '.png')).convert('RGB'))
    d1.parent.mkdir(parents=True, exist_ok=True); d2.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray((vangogh3(rgb, v) * 255).round().astype(np.uint8)).save(d1); Image.fromarray((ink3(rgb) * 255).round().astype(np.uint8)).save(d2)
    if i % 100 == wi: print(split, i, len(stems), flush=True)
print('done', split, wi, flush=True)
