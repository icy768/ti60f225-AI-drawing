"""Recalibrate a frozen FP32 model without modifying weights or the source run."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps
import torch

from tinystyle import TinyStyleNet, QCfg
from train import image_list


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--checkpoint', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--ncal', type=int, default=100)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(4)
    torch.manual_seed(20261004)
    ck = torch.load(args.checkpoint, map_location='cpu', weights_only=False)
    dev = 'cuda' if torch.cuda.is_available() else 'cpu'
    net = TinyStyleNet(**ck['cfg']).to(dev).eval()
    net.load_state_dict(ck['sd'])
    QCfg.enabled = QCfg.observe = False
    train, validation = image_list()
    chosen = np.random.RandomState(20261004).choice(len(train), args.ncal, replace=False)
    files = [train[i] for i in chosen]
    assert not set(files) & set(validation)
    values = [[] for _ in net.layers]
    hooks = []
    for i, layer in enumerate(net.layers):
        if layer.aq.fixed is not None:
            continue
        def observe(module, inputs, index=i):
            # Deterministic spatial sample; retain the largest per-image/style
            # percentile so a high-range style is not overwritten by another.
            flat = inputs[0].detach().float().flatten()
            flat = flat[::max(1, flat.numel() // 200000)]
            values[index].append(float(torch.quantile(flat, 0.9999)))
        hooks.append(layer.aq.register_forward_pre_hook(observe))
    with torch.no_grad():
        for i, path in enumerate(files):
            im = ImageOps.fit(Image.open(path).convert('RGB'), (640, 480), method=Image.Resampling.BILINEAR)
            x = torch.from_numpy(np.asarray(im).copy()).permute(2, 0, 1)[None].to(dev).float() / 255
            for s in range(ck['cfg']['n_styles']):
                net(x, torch.tensor([s], device=dev))
            if (i + 1) % 10 == 0:
                print('CAL', i + 1, '/', len(files), flush=True)
    for hook in hooks:
        hook.remove()
    ranges = []
    for i, layer in enumerate(net.layers):
        if not values[i]:
            continue
        before = float(layer.aq.rmax)
        after = max(max(values[i]), 1e-6)
        layer.aq.rmax.fill_(after)
        ranges.append(dict(layer=layer.spec['name'], before=before, after=after))
    sd = {k: v.detach().cpu() for k, v in net.state_dict().items()}
    assert all(torch.equal(v, ck['sd'][k]) for k, v in sd.items() if not k.endswith('.aq.rmax'))
    ck['sd'] = sd
    ck['qat'] = False
    ck['delivery_calibration'] = 'max of per-image/style sampled 99.99th percentiles; 640x480'
    torch.save(ck, out / 'student.pt')
    report = dict(source_sha256=hashlib.sha256(Path(args.checkpoint).read_bytes()).hexdigest(),
                  checkpoint_sha256=hashlib.sha256((out / 'student.pt').read_bytes()).hexdigest(),
                  image_count=len(files), styles=ck.get('styles'), seed=20261004,
                  images=[Path(f).name for f in files], method=ck['delivery_calibration'],
                  ranges=ranges, weights_unchanged=True, validation_disjoint=True)
    (out / 'calibration.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
