"""Create same-input comparison of Skill teachers and v20 FP32/INT8 outputs."""
from pathlib import Path
import hashlib
import json

import numpy as np
from PIL import Image, ImageDraw, ImageOps
import torch

import golden
from tinystyle import QCfg, TinyStyleNet
from train import ROOT


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rgb(y: torch.Tensor) -> np.ndarray:
    return (y[0].permute(1, 2, 0).detach().cpu().numpy() * 255).round().clip(0, 255).astype(np.uint8)


def main() -> None:
    root = Path(ROOT)
    out = root / "audits" / "v20_city_skill_comparison"
    out.mkdir(parents=True, exist_ok=False)
    inp = root / "audits" / "v15_v6_restart_20261005" / "new_scenes_comparisons" / "city_street_000000026204_input.png"
    skill_dir = root / "audits" / "skill_network_comparison"
    rows = [
        ("van_gogh", skill_dir / "city_street_skill_vangogh_imagegen.png"),
        ("ukiyo_e", skill_dir / "city_street_skill_ukiyoe_imagegen.png"),
        ("ink_landscape", skill_dir / "city_street_skill_ink_imagegen.png"),
    ]
    ck = torch.load(root / "runs" / "art_styles_c24_v19_expanded_skill" / "student.pt", map_location="cpu", weights_only=False)
    QCfg.enabled = QCfg.observe = False
    net = TinyStyleNet(**ck["cfg"]).cuda().eval()
    net.load_state_dict(ck["sd"])
    q = golden.load(str(root / "audits" / "v20_qat900_export"))
    source = np.asarray(Image.open(inp).convert("RGB"))
    x = torch.from_numpy(source.copy()).permute(2, 0, 1)[None].cuda().float() / 255
    W, H = 360, 270
    sheet = Image.new("RGB", (4 * W, 3 * (H + 34)), "white")
    draw = ImageDraw.Draw(sheet)
    labels = ["Input", "Skill teacher", "v20 FP32", "v20 INT8"]
    manifest_rows = []
    for ri, (style, skill_path) in enumerate(rows):
        si = ck["styles"].index(style)
        with torch.no_grad():
            fp32 = rgb(net(x, torch.tensor([si], device="cuda")))
        int8, _, _ = golden.run(q, source, si)
        skill = np.asarray(Image.open(skill_path).convert("RGB"))
        for ci, arr in enumerate((source, skill, fp32, int8)):
            im = ImageOps.contain(Image.fromarray(arr), (W, H), Image.Resampling.LANCZOS)
            x0 = ci * W + (W - im.width) // 2
            y0 = ri * (H + 34) + 34 + (H - im.height) // 2
            sheet.paste(im, (x0, y0))
            draw.text((ci * W + 6, ri * (H + 34) + 8), labels[ci], fill="black")
        draw.text((4 * W - 96, ri * (H + 34) + 8), style, fill="black")
        fp_path = out / f"city_street_{style}_v20_fp32.png"
        int_path = out / f"city_street_{style}_v20_int8.png"
        Image.fromarray(fp32).save(fp_path)
        Image.fromarray(int8).save(int_path)
        manifest_rows.append({
            "style": style,
            "skill_teacher": str(skill_path.resolve()),
            "skill_sha256": sha256(skill_path),
            "v20_fp32": str(fp_path.resolve()),
            "v20_int8": str(int_path.resolve()),
        })
    sheet_path = out / "city_street_skill_vs_v20.jpg"
    sheet.save(sheet_path, quality=96)
    manifest = {
        "input": str(inp.resolve()),
        "input_sha256": sha256(inp),
        "rows": manifest_rows,
        "model_float": "runs/art_styles_c24_v19_expanded_skill/student.pt",
        "model_qat": "runs/art_styles_c24_v20_qat900_soft1/student.pt",
        "qparams": "audits/v20_qat900_export",
        "notes": "Skill teacher images are synthetic visual references; they are not paired ground truth or a claim of artwork copyright status.",
    }
    (out / "comparison_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(sheet_path.resolve())


if __name__ == "__main__":
    main()
