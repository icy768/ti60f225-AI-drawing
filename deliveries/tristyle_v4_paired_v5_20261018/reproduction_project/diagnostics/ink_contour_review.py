"""Audit saved lossless ink outputs; fixed17 is inference-only, never optimized.

PSNR/SSIM to an accepted stylized anchor measure retention, not artistic quality.
PSNR/SSIM to input luminance measure content resemblance, not style correctness.
There is no registered artistic ground-truth image for these scenes.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw
from skimage.metrics import peak_signal_noise_ratio, structural_similarity

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "reports/v4_ink_contour_01"
OUT = RUN / "review"


def gray(a):
    return a @ np.array([.299, .587, .114], dtype=np.float64)


def similarity(a, b):
    return {"psnr_db": float(peak_signal_noise_ratio(a, b, data_range=1.)),
            "ssim": float(structural_similarity(a, b, data_range=1.,
                channel_axis=2 if a.ndim == 3 else None,
                gaussian_weights=True, sigma=1.5, use_sample_covariance=False))}


def gradients(a):
    a = cv2.GaussianBlur(a, (0, 0), 2., borderType=cv2.BORDER_REFLECT_101)
    return (cv2.Sobel(a, cv2.CV_64F, 1, 0, ksize=3) / 8.,
            cv2.Sobel(a, cv2.CV_64F, 0, 1, ksize=3) / 8.)


def features(a, inp):
    g, x = gray(a), gray(inp)
    dx, dy = gradients(g); ix, iy = gradients(x)
    mag, im = np.hypot(dx, dy), np.hypot(ix, iy)
    mask = im > max(float(np.quantile(im, .75)), .006)
    ori = np.abs(dx * ix + dy * iy) / (mag * im + 1e-8)
    return {"broad_contour_strength": float(mag[mask].mean()),
            "input_contour_orientation": float(ori[mask].mean()),
            "white_fraction_luma_gt_085": float((g > .85).mean()),
            "dark_fraction_luma_lt_025": float((g < .25).mean()),
            "mean_chroma": float(np.abs(a - g[..., None]).mean())}


def main():
    OUT.mkdir(exist_ok=True)
    manifest = json.loads((ROOT / "data/fixed_test_manifest.json").read_text())
    attachment = Path("D:/Temp/codex-clipboard-d171893e-165d-406a-9108-8e05af4b0f52.png")
    original = ROOT / "reports/v4_v3_refine_01/000600/ink_V3_vs_pilot17.jpg"
    a, b = np.array(Image.open(attachment).convert("RGB")), np.array(Image.open(original).convert("RGB"))
    assert a.shape == b.shape and np.array_equal(a, b)
    evidence = {"attachment_decoded_pixel_match": True, "shape": list(a.shape),
                "student_checkpoint": "experiments/v4_v3_refine_01/step_000600.pt",
                "matched_gallery": str(original.relative_to(ROOT)),
                "decoded_rgb_sha256": hashlib.sha256(a.tobytes()).hexdigest()}
    (OUT / "attachment_provenance.json").write_text(json.dumps(evidence, indent=2))
    rows = []
    sheets = []
    crops = []
    for offset in range(0, len(manifest), 6):
        names = list(manifest)[offset:offset + 6]
        sheet = Image.new("RGB", (5 * 256, len(names) * 220), "white")
        draw = ImageDraw.Draw(sheet)
        for ri, name in enumerate(names):
            stem = Path(name).stem
            inp_img = Image.open(manifest[name]["path"]).convert("RGB")
            inp = np.array(inp_img).astype(np.float64) / 255.
            anchor_img = Image.open(RUN / "000600" / f"{stem}_ink_CURRENT.png").convert("RGB")
            anchor = np.array(anchor_img).astype(np.float64) / 255.
            base_metrics = similarity(gray(inp), gray(anchor))
            imgs = [inp_img, anchor_img]
            labels = [f"{stem} INPUT", "ACCEPTED INK ANCHOR"]
            for step in (600, 1200, 1800):
                folder = RUN / f"{step:06d}"
                cand_path = folder / f"{stem}_ink_CANDIDATE.png"
                ci = Image.open(cand_path).convert("RGB")
                c = np.array(ci).astype(np.float64) / 255.
                assert np.array_equal(np.array(anchor_img), np.array(Image.open(folder / f"{stem}_ink_CURRENT.png")))
                inp_scores = similarity(gray(inp), gray(c))
                feats, base_feats = features(c, inp), features(anchor, inp)
                rows.append({"scene": stem, "step": step, "shape": list(c.shape),
                    "candidate_sha256": hashlib.sha256(cand_path.read_bytes()).hexdigest(),
                    "to_anchor_RGB": similarity(anchor, c),
                    "to_input_luma": inp_scores, "anchor_to_input_luma": base_metrics,
                    "input_psnr_delta_db": inp_scores["psnr_db"] - base_metrics["psnr_db"],
                    "input_ssim_delta": inp_scores["ssim"] - base_metrics["ssim"],
                    "candidate_features": feats, "anchor_features": base_feats,
                    "broad_contour_gain_percent": (feats["broad_contour_strength"] / base_feats["broad_contour_strength"] - 1.) * 100.})
                imgs.append(ci); labels.append(f"CANDIDATE step {step}")
            for col, (im, label) in enumerate(zip(imgs, labels)):
                im = im.copy(); im.thumbnail((256, 190), Image.Resampling.LANCZOS)
                sheet.paste(im, (col * 256, ri * 220))
                draw.text((col * 256 + 2, ri * 220 + 194), label, fill="black")
            w, h = inp_img.size
            # Fixed center crop for all scenes and checkpoints, without searching
            # for a region that favors a candidate. Native pixel size is retained.
            box = (max(0, w // 2 - 128), max(0, h // 2 - 128), min(w, w // 2 + 128), min(h, h // 2 + 128))
            crop = Image.new("RGB", (1024, 280), "white"); cd = ImageDraw.Draw(crop)
            for col, im in enumerate(imgs[1:]):
                crop.paste(im.crop(box), (col * 256, 0))
                cd.text((col * 256 + 2, 260), labels[col + 1], fill="black")
            crop.save(OUT / f"{stem}_native_crop.png")
            crops.append(stem)
        fn = f"overview_{offset // 6 + 1}.jpg"
        sheet.save(OUT / fn, quality=95); sheets.append(fn)
    summary = []
    for step in (600, 1200, 1800):
        rs = [r for r in rows if r["step"] == step]
        summary.append({"step": step, "scenes": len(rs),
            "mean_psnr_to_anchor_RGB_db": float(np.mean([r["to_anchor_RGB"]["psnr_db"] for r in rs])),
            "mean_ssim_to_anchor_RGB": float(np.mean([r["to_anchor_RGB"]["ssim"] for r in rs])),
            "mean_input_luma_psnr_delta_db": float(np.mean([r["input_psnr_delta_db"] for r in rs])),
            "mean_input_luma_ssim_delta": float(np.mean([r["input_ssim_delta"] for r in rs])),
            "input_luma_psnr_improved_scenes": sum(r["input_psnr_delta_db"] > 0 for r in rs),
            "input_luma_ssim_improved_scenes": sum(r["input_ssim_delta"] > 0 for r in rs),
            "mean_broad_contour_gain_percent": float(np.mean([r["broad_contour_gain_percent"] for r in rs])),
            "min_broad_contour_gain_percent": float(min(r["broad_contour_gain_percent"] for r in rs)),
            "max_broad_contour_gain_percent": float(max(r["broad_contour_gain_percent"] for r in rs))})
    result = {"protocol": "Lossless uint8 native outputs, full-frame including borders, per-scene unweighted mean; no resized metric images",
        "limitations": ["No registered artistic ground truth", "Anchor metrics measure retention", "Input luma metrics measure content resemblance", "Contour strength can increase through unwanted sharpening; independent visual review required"],
        "promoted": False, "summary": summary, "rows": rows}
    (OUT / "metrics.json").write_text(json.dumps(result, indent=2))
    (OUT / "INDEX.html").write_text("<!doctype html><meta charset='utf-8'><title>Ink contour independent review</title>"
        "<h1>Ink contour review</h1><p>Input / accepted ink / 600 / 1200 / 1800. Metrics are not artistic acceptance.</p>"
        + "".join(f"<p><img width='1280' src='{f}'></p>" for f in sheets)
        + "<h2>Native center crops</h2>" + "".join(f"<p>{s}<br><img src='{s}_native_crop.png'></p>" for s in crops)
        + "<p><a href='metrics.json'>Full metric protocol and per-scene results</a></p>", encoding="utf-8")
    print(json.dumps({"attachment": evidence, "summary": summary}, indent=2))


if __name__ == "__main__":
    main()
