"""Reproducible VGA visual diagnostics; no artistic score or board-FPS claim."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageDraw, ImageOps

from tinystyle import QCfg, TinyStyleNet
from train import ROOT, image_list


def statistics(rgb):
    z = rgb.astype(np.float32) / 255
    lum = .299*z[:, :, 0] + .587*z[:, :, 1] + .114*z[:, :, 2]
    chroma = z.max(2) - z.min(2)
    dx = np.abs(np.diff(lum, axis=1)); dy = np.abs(np.diff(lum, axis=0))
    return dict(chroma_range_255=float(chroma.mean()*255), luma_mean_255=float(lum.mean()*255),
                paper_like_fraction=float(((lum >= .90) & (chroma <= .08)).mean()),
                dark_fraction=float((lum < .20).mean()),
                gradient_mean_255=float((dx.mean()+dy.mean())*255),
                flat_neighbor_fraction=float(((dx[:-1] < .01) & (dy[:, :-1] < .01)).mean()),
                quantized_rgb_bins=int(len(np.unique((rgb//32).reshape(-1, 3), axis=0))))


def tensor(im, device):
    return torch.from_numpy(np.asarray(im).copy()).permute(2, 0, 1)[None].to(device).float()/255


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--out", default="")
    ap.add_argument("--count", type=int, default=16)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--save_count", type=int, default=16)
    ap.add_argument("--camera", default="")
    args = ap.parse_args()
    torch.set_num_threads(4)
    checkpoint = Path(ROOT)/args.checkpoint
    out = Path(ROOT)/args.out if args.out else checkpoint.parent/f"eval_{checkpoint.stem}"
    out.mkdir(parents=True, exist_ok=True)
    ck = torch.load(checkpoint, map_location="cpu", weights_only=False)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    net = TinyStyleNet(**ck["cfg"]).to(device).eval(); net.load_state_dict(ck["sd"])
    QCfg.enabled = False; QCfg.observe = False
    train, held = image_list()
    files = held[args.offset:args.offset+args.count]
    assert not set(files).intersection(train)
    if args.camera:
        files.append(args.camera)
    records = []; rows = []
    with torch.no_grad():
        for image_index, f in enumerate(files):
            keep_image = image_index < args.save_count or f == args.camera
            im = ImageOps.fit(Image.open(f).convert("RGB"), (640, 480), Image.Resampling.BILINEAR)
            x = tensor(im, device); row = [im]
            record = dict(image=str(f), input=statistics(np.asarray(im)), styles={})
            for si, name in enumerate(ck["styles"]):
                y = net(x, torch.tensor([si], device=device)).clamp(0, 1)
                rgb = (y[0].permute(1, 2, 0).cpu().numpy()*255).round().astype(np.uint8)
                yi = Image.fromarray(rgb); row.append(yi)
                if keep_image:
                    yi.save(out/f"{Path(f).stem}_{name}.png")
                record["styles"][name] = statistics(rgb)
            if keep_image:
                im.save(out/f"{Path(f).stem}_input.png")
                rows.append(row)
            records.append(record)
            if (image_index+1) % 25 == 0:
                print(f"Evaluated {image_index+1}/{len(files)} VGA inputs", flush=True)
    labels = ["Input", "Van Gogh", "Ukiyo-e", "Ink wash"]
    for start in range(0, len(rows), 4):
        group = rows[start:start+4]
        sheet = Image.new("RGB", (1280, 268*len(group)), "white")
        draw = ImageDraw.Draw(sheet)
        for i, row in enumerate(group):
            for j, im in enumerate(row):
                draw.text((320*j+5, 268*i+7), labels[j], fill="black")
                sheet.paste(im.resize((320, 240), Image.Resampling.LANCZOS), (320*j, 268*i+28))
        sheet.save(out/f"comparison_{start//4+1:02d}.jpg", quality=95)
    means = {name: {k: float(np.mean([r["styles"][name][k] for r in records[:args.count]]))
                    for k in records[0]["input"]} for name in ck["styles"]}
    result = dict(checkpoint=str(checkpoint), sha256=hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
                  n_coco=min(args.count, len(held)-args.offset), size=[640, 480], fp32=True,
                  means=means, records=records,
                  note="Content split was excluded from training. Repeatedly viewed subsets are development data. "
                  "Chroma, paper fraction and gradients are diagnostic proxies, not art scores. "
                  "Camera monitor photograph, when provided, is not a raw camera frame or video.")
    (out/"summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(dict(output=str(out), means=means), indent=2))


if __name__ == "__main__":
    main()
