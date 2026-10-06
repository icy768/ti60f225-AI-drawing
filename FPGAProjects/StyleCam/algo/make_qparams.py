"""Generate a fixed integer contract for one checkpoint from calibration frames."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

import golden
from train import ROOT, image_list


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--checkpoint", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--count", type=int, default=100)
    args = p.parse_args()
    root = Path(ROOT)
    out = root / args.out
    if out.with_suffix(".json").exists() or out.with_suffix(".npz").exists():
        raise FileExistsError(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    train, held = image_list()
    if args.count > len(train):
        raise ValueError("calibration count exceeds training split")
    files = train[:args.count]
    imgs = [np.asarray(ImageOps.fit(Image.open(f).convert("RGB"), (640, 480), Image.Resampling.BILINEAR))
            for f in files]
    q = golden.export_float(str(root / args.checkpoint))
    golden.calibrate(q, imgs, len(q["styles"]), margin=2.0)
    golden.save(q, str(out))
    report = {
        "checkpoint": args.checkpoint,
        "checkpoint_sha256": hashlib.sha256((root / args.checkpoint).read_bytes()).hexdigest(),
        "contract_json": str(out.with_suffix(".json")),
        "contract_npz": str(out.with_suffix(".npz")),
        "count": len(files),
        "size": [640, 480],
        "split": "training; disjoint from held-out evaluation",
        "margin": 2.0,
        "images": [Path(f).name for f in files],
        "layers": [{"name": n, "R": int(r), "S": int(s)} for n, r, s in golden.calibrate(golden.export_float(str(root / args.checkpoint)), imgs, len(q["styles"]), margin=2.0)]
    }
    (out.parent / (out.stem + "_calibration.json")).write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
