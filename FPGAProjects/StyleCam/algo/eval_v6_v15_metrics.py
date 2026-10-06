"""Paired v6/v15 FP32 evaluation on the identical held-out VGA split.

PSNR/SSIM are reported against the v6 output and the input only as fidelity
diagnostics.  They are not an official style-quality threshold.  Style
structure proxies are computed independently from the source image.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageOps
from skimage.metrics import peak_signal_noise_ratio, structural_similarity

from eval_art_region_v10 import inspect
from eval_art_styles_v4 import statistics, tensor
from tinystyle import QCfg, TinyStyleNet
from train import ROOT, image_list


def load(path):
    ck = torch.load(path, map_location="cpu", weights_only=False)
    net = TinyStyleNet(**ck["cfg"]).cuda().eval()
    net.load_state_dict(ck["sd"])
    return ck, net


def rgb(y):
    return (y[0].permute(1, 2, 0).detach().cpu().numpy() * 255).round().clip(0, 255).astype(np.uint8)


def metric(a, b):
    return {
        "psnr_db": float(peak_signal_noise_ratio(a, b, data_range=255)),
        "ssim": float(structural_similarity(a, b, channel_axis=2, data_range=255)),
        "mae_255": float(np.abs(a.astype(np.float32) - b.astype(np.float32)).mean()),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--v6", required=True)
    p.add_argument("--v15", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--count", type=int, default=200)
    p.add_argument("--save-count", type=int, default=16)
    args = p.parse_args()
    root = Path(ROOT)
    out = root / args.out
    out.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(4)
    QCfg.enabled = QCfg.observe = False
    ck6, n6 = load(root / args.v6)
    ck15, n15 = load(root / args.v15)
    if ck6["cfg"] != ck15["cfg"] or ck6["styles"] != ck15["styles"]:
        raise ValueError("v6/v15 graph or style contract differs")
    _, files = image_list()
    files = files[:args.count]
    styles = ck6["styles"]
    records = []
    sums = {s: {"v6": [], "v15": [], "v15_vs_v6": [], "v6_vs_input": [], "v15_vs_input": []} for s in styles}
    with torch.no_grad():
        for j, f in enumerate(files):
            im = ImageOps.fit(Image.open(f).convert("RGB"), (640, 480), Image.Resampling.BILINEAR)
            source = np.asarray(im)
            x = tensor(im, "cuda")
            rec = {"image": Path(f).name, "styles": {}}
            for si, style in enumerate(styles):
                st = torch.tensor([si], device="cuda")
                a = rgb(n6(x, st).clamp(0, 1))
                b = rgb(n15(x, st).clamp(0, 1))
                row = {
                    "v6_stats": statistics(a),
                    "v15_stats": statistics(b),
                    "v6_structure": inspect(source, a, style),
                    "v15_structure": inspect(source, b, style),
                    "v15_vs_v6": metric(a, b),
                    "v6_vs_input": metric(source, a),
                    "v15_vs_input": metric(source, b),
                }
                rec["styles"][style] = row
                for key in ("v6_vs_input", "v15_vs_input", "v15_vs_v6"):
                    sums[style][key].append(row[key])
            records.append(rec)
            if j < args.save_count:
                for label, arr in (("input", source), ("v6", None), ("v15", None)):
                    if label == "input":
                        Image.fromarray(arr).save(out / f"{j:03}_input.png")
                for si, style in enumerate(styles):
                    st = torch.tensor([si], device="cuda")
                    Image.fromarray(rgb(n6(x, st))).save(out / f"{j:03}_{style}_v6.png")
                    Image.fromarray(rgb(n15(x, st))).save(out / f"{j:03}_{style}_v15.png")
            if (j + 1) % 25 == 0:
                print(f"Evaluated {j + 1}/{len(files)}", flush=True)

    means = {}
    for style in styles:
        means[style] = {}
        for key in ("v15_vs_v6", "v6_vs_input", "v15_vs_input"):
            rows = sums[style][key]
            means[style][key] = {metric_name: float(np.mean([r[metric_name] for r in rows]))
                                 for metric_name in ("psnr_db", "ssim", "mae_255")}
        for side in ("v6_structure", "v15_structure"):
            rows = [r["styles"][style][side] for r in records]
            means[style][side] = {k: float(np.mean([r[k] for r in rows])) for k in rows[0]}
        for side in ("v6_stats", "v15_stats"):
            rows = [r["styles"][style][side] for r in records]
            means[style][side] = {k: float(np.mean([r[k] for r in rows])) for k in rows[0]}

    report = {
        "protocol": "same first N held-out COCO RGB images, ImageOps.fit 640x480, FP32 uint8 outputs",
        "caveat": "PSNR/SSIM are fidelity diagnostics against v6 or the source photo; no official absolute threshold was supplied by the competition",
        "graph_unchanged": True,
        "v6": {"path": args.v6, "sha256": hashlib.sha256((root / args.v6).read_bytes()).hexdigest()},
        "v15": {"path": args.v15, "sha256": hashlib.sha256((root / args.v15).read_bytes()).hexdigest()},
        "count": len(records),
        "means": means,
        "records": records,
    }
    (out / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"out": str(out), "means": means}, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
