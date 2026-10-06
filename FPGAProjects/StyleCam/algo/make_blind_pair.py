"""Create anonymized A/B sheets for a paired v6/candidate review."""
import argparse
import hashlib
import json
import random
from pathlib import Path

from PIL import Image, ImageDraw

from train import ROOT


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source", required=True, help="directory produced by eval_v6_v15_metrics")
    p.add_argument("--out", required=True)
    p.add_argument("--count", type=int, default=16)
    args = p.parse_args()
    root = Path(ROOT)
    source, out = root / args.source, root / args.out
    out.mkdir(parents=True, exist_ok=False)
    styles = ("van_gogh", "ukiyo_e", "ink_landscape")
    rng = random.Random(20261005)
    key = {}
    for j in range(args.count):
        for style in styles:
            order = ["v6", "v15"]
            rng.shuffle(order)
            key[f"{style}_{j:03}"] = order
            sheet = Image.new("RGB", (960, 270), "white")
            draw = ImageDraw.Draw(sheet)
            sheet.paste(Image.open(source / f"{j:03}_input.png").convert("RGB").resize((320, 240)), (0, 30))
            draw.text((5, 8), f"{style} / input", fill="black")
            for col, label in enumerate(order, 1):
                path = source / f"{j:03}_{style}_{label}.png"
                sheet.paste(Image.open(path).convert("RGB").resize((320, 240)), (320 * col, 30))
                draw.text((320 * col + 5, 8), f"{style} / {chr(64 + col)}", fill="black")
            sheet.save(out / f"{style}_{j:03}.jpg", quality=96)
    manifest = {"source": args.source, "count": args.count, "styles": styles,
                "seed": 20261005, "blind_key": key,
                "sheet_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in sorted(out.glob("*.jpg"))}}
    (out / "blind_key.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"out": str(out), "sheets": len(list(out.glob("*.jpg")))}, ensure_ascii=False))


if __name__ == "__main__":
    main()
