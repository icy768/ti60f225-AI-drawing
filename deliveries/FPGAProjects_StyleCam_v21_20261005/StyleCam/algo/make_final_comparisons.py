"""Make readable before/after montages for real held-out images."""
import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
import torch

import golden
from tinystyle import QCfg, TinyStyleNet
from train import ROOT


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--v6", required=True)
    p.add_argument("--final", required=True)
    p.add_argument("--qparams", required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--count", type=int, default=4)
    a = p.parse_args()
    root = Path(ROOT)
    out = root / a.out
    out.mkdir(parents=True, exist_ok=False)
    c6 = torch.load(root / a.v6, map_location="cpu", weights_only=False)
    cf = torch.load(root / a.final, map_location="cpu", weights_only=False)
    n6 = TinyStyleNet(**c6["cfg"]).cuda().eval(); n6.load_state_dict(c6["sd"])
    nf = TinyStyleNet(**cf["cfg"]).cuda().eval(); nf.load_state_dict(cf["sd"])
    q = golden.load(str(root / a.qparams))
    QCfg.enabled = QCfg.observe = False
    styles = c6["styles"]
    source = root / a.source
    files = sorted(source.glob("*_input.png"))[:a.count]
    for path in files:
        stem = path.stem.replace("_input", "")
        im = Image.open(path).convert("RGB")
        x = torch.from_numpy(np.asarray(im).copy()).permute(2, 0, 1)[None].cuda().float() / 255
        for si, style in enumerate(styles):
            st = torch.tensor([si], device="cuda")
            with torch.no_grad():
                y6 = (n6(x, st)[0].permute(1, 2, 0).cpu().numpy() * 255).round().clip(0, 255).astype(np.uint8)
                yf = (nf(x, st)[0].permute(1, 2, 0).cpu().numpy() * 255).round().clip(0, 255).astype(np.uint8)
            yi, _, _ = golden.run(q, np.asarray(im).copy(), si)
            # Preserve full-resolution outputs for inspection, not just thumbnails.
            im.save(out / f"{stem}_input.png")
            Image.fromarray(y6).save(out / f"{stem}_{style}_v6.png")
            Image.fromarray(yf).save(out / f"{stem}_{style}_fp32.png")
            Image.fromarray(yi).save(out / f"{stem}_{style}_int8.png")
            sheet = Image.new("RGB", (1280, 285), "white")
            draw = ImageDraw.Draw(sheet)
            panels = [("Input", np.asarray(im)), ("v6", y6), ("Final FP32", yf), ("Final INT8", yi)]
            for col, (label, arr) in enumerate(panels):
                thumb = Image.fromarray(arr).resize((320, 240), Image.Resampling.LANCZOS)
                sheet.paste(thumb, (320 * col, 35))
                draw.text((320 * col + 6, 10), f"{label} / {style}", fill="black")
            sheet.save(out / f"{stem}_{style}.jpg", quality=96)
    print(out)


if __name__ == "__main__":
    main()
