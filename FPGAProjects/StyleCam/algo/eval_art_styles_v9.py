"""Compare v8/v9 against an untouched AIC oil painting and COCO content."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps
import torch
import torch.nn.functional as F

from art_material_v7 import PatchBank
from eval_art_styles_v4 import statistics, tensor
from tinystyle import TinyStyleNet, QCfg, macs_per_pixel
from train import ROOT, image_list
from train_art_styles import gram
from train_art_styles_v4 import ArtFeatures, NAMES


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--models', nargs='+', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--count', type=int, default=24)
    args = p.parse_args()
    root = Path(ROOT)
    out = root / args.out
    out.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(4)
    QCfg.enabled = QCfg.observe = False
    manifest = json.loads((root/'dataset_v2/manifests/aic_v9.json').read_text(encoding='utf-8'))
    held = [r for r in manifest if r['role'] == 'holdout']
    assert len(held) == 1
    reference_path = root/'dataset_v2'/held[0]['path']
    assert digest(reference_path) == held[0]['sha256']
    reference = ImageOps.fit(Image.open(reference_path).convert('RGB'), (256, 256), Image.Resampling.LANCZOS)
    feature_net = ArtFeatures().cuda().eval()
    with torch.no_grad():
        reference_features = feature_net(tensor(reference, 'cuda'))
        reference_grams = [gram(f) for f in reference_features]
        reference_patches = PatchBank([reference_features])
    train, dev = image_list()
    files = dev[:args.count]
    assert files and not set(files) & set(train)
    models = {}
    for cp in args.models:
        path = root/cp
        ck = torch.load(path, map_location='cpu', weights_only=False)
        assert ck['styles'] == NAMES
        n = TinyStyleNet(**ck['cfg']).cuda().eval()
        n.load_state_dict(ck['sd'])
        models[path.parent.name] = (path, n)
    baselines = None
    result = dict(development_set=True, content_count=len(files), resolution=[640, 480],
                  aic_holdout=dict(id=held[0]['id'], sha256=held[0]['sha256'], path=str(reference_path)),
                  models={})
    for name, (path, net) in models.items():
        rows = []
        outputs = []
        with torch.no_grad():
            for f in files:
                im = ImageOps.fit(ImageOps.exif_transpose(Image.open(f)).convert('RGB'), (640, 480), Image.Resampling.BILINEAR)
                x = tensor(im, 'cuda')
                content_features = feature_net(F.interpolate(x, size=(256, 256), mode='bilinear', align_corners=False))
                row = {'file': Path(f).name, 'styles': {}}
                current = []
                for si, style in enumerate(NAMES):
                    y = net(x, torch.tensor([si], device='cuda'))
                    current.append(y.cpu())
                    rgb = (y[0].permute(1, 2, 0).cpu().numpy()*255).round().astype(np.uint8)
                    metrics = statistics(rgb)
                    if si == 0:
                        features = feature_net(F.interpolate(y, size=(256, 256), mode='bilinear', align_corners=False))
                        metrics['holdout_gram_relative'] = float(sum(
                            F.mse_loss(gram(a), b)/b.square().mean().clamp_min(1e-8)
                            for a, b in zip(features, reference_grams))/4)
                        metrics['holdout_patch_relative'] = float(reference_patches.loss(features[1]))
                        metrics['content_relu3_relative'] = float(F.mse_loss(features[2], content_features[2]) /
                                                                  content_features[2].square().mean().clamp_min(1e-6))
                    if baselines is not None:
                        metrics['change_from_v8_mae_255'] = float(F.l1_loss(y, baselines[len(rows)][si].cuda())*255)
                    row['styles'][style] = metrics
                outputs.append(current)
                rows.append(row)
        if baselines is None:
            baselines = outputs
        means = {style: {key: float(np.mean([r['styles'][style][key] for r in rows]))
                         for key in rows[0]['styles'][style]} for style in NAMES}
        result['models'][name] = dict(checkpoint=str(path), sha256=digest(path),
                                      cfg=net.cfg, params=sum(x.numel() for x in net.parameters()),
                                      conv_MACs_VGA=macs_per_pixel(net.specs)[0]*640*480,
                                      means=means, records=rows)
        print(json.dumps({'model': name, 'means': means}), flush=True)
    (out/'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
