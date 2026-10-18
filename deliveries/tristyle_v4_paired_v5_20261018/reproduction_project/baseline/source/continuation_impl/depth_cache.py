"""Training-only relative inverse-depth guidance from newly fetched Apache2 Small.
Never loads or optimizes fixed tests/heldout video. This teacher is not deployed.
"""
import argparse, hashlib, json, pathlib, sys, time
import numpy as np
import torch
import cv2
from PIL import Image
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'external/depth_v2'))
from depth_anything_v2.dpt import DepthAnythingV2


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--split', choices=('train', 'validation', 'all'), default='all')
    ap.add_argument('--device', default='cuda'); ap.add_argument('--max-size', type=int, default=392)
    ap.add_argument('--limit', type=int, default=0); ap.add_argument('--out', default='data/continuation_depth')
    a = ap.parse_args(); torch.set_num_threads(3)
    model = DepthAnythingV2(encoder='vits', features=64, out_channels=[48, 96, 192, 384])
    weights = ROOT / 'teachers/weights/depth_anything_v2_vits.pth'
    model.load_state_dict(torch.load(weights, map_location='cpu', weights_only=True), strict=True)
    model = model.to(a.device).eval(); out = ROOT / a.out; out.mkdir(parents=True, exist_ok=True)
    (out / 'config.json').write_text(json.dumps({**vars(a), 'weights_sha256': hashlib.sha256(weights.read_bytes()).hexdigest(),
        'license': 'Apache-2.0 Small only; sources/depth_v2_model_info.json and external/depth_v2/LICENSE',
        'kind': 'relative inverse depth, higher=near; not metric and not a deployed input',
        'normalization': 'RGB ImageNet; aspect preserved, upper bounded long side, dimensions rounded to multiple14; output interpolated to source; quantiles1/99 normalize'}, indent=2))
    denied = set(json.loads((ROOT / 'data/test/coco_test_ids.json').read_text())); start = time.time(); n = 0
    mu = torch.tensor([.485, .456, .406], device=a.device).view(1, 3, 1, 1)
    sd = torch.tensor([.229, .224, .225], device=a.device).view(1, 3, 1, 1)
    for split in (('validation', 'train') if a.split == 'all' else (a.split,)):
        dst = out / split; dst.mkdir(exist_ok=True)
        for p in sorted((ROOT / 'data/claude_targets/content' / split).glob('*.png')):
            assert int(p.stem) not in denied
            q = dst / (p.stem + '.npz')
            if q.exists(): continue
            im = np.array(Image.open(p).convert('RGB'), copy=True); h, w = im.shape[:2]
            scale = min(1., a.max_size / max(h, w)); nh = max(28, round(h * scale / 14) * 14); nw = max(28, round(w * scale / 14) * 14)
            small = cv2.resize(im, (nw, nh), interpolation=cv2.INTER_CUBIC)
            x = torch.from_numpy(small).permute(2, 0, 1)[None].float().to(a.device) / 255
            with torch.inference_mode(), torch.autocast('cuda', enabled=a.device == 'cuda'):
                depth = model((x - mu) / sd)
            depth = depth[0].float().cpu().numpy(); assert np.isfinite(depth).all()
            lo, hi = np.quantile(depth, [.01, .99]); depth = np.clip((depth - lo) / max(hi - lo, 1e-6), 0, 1)
            depth = cv2.resize(depth, (w, h), interpolation=cv2.INTER_CUBIC).clip(0, 1)
            np.savez_compressed(q, near=depth.astype(np.float16), input_size=np.array([nw, nh]))
            n += 1
            if n == 1 or n % 50 == 0: print(json.dumps({'split': split, 'done': n, 'elapsed': time.time() - start, 'last': p.name, 'input_size': [nw, nh]}), flush=True)
            if a.limit and n >= a.limit: break
        if a.limit and n >= a.limit: break
    (out / 'finished.json').write_text(json.dumps({'done_this_run': n, 'elapsed': time.time() - start, 'args': vars(a)}, indent=2))
    print('FINISHED', n, time.time() - start, flush=True)


if __name__ == '__main__': main()
