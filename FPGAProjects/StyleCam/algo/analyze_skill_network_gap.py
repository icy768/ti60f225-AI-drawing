"""Quantify visual differences on the same city-street example.

Skill image-edit outputs are resized/cropped to 640x480 for diagnostics. Their
PSNR/SSIM against StyleCam are alignment diagnostics only, not quality labels.
"""
from pathlib import Path
import json
import numpy as np
from PIL import Image, ImageOps
from skimage.metrics import structural_similarity


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "audits" / "skill_network_comparison"
BASE = ROOT / "audits" / "v15_v6_restart_20261005" / "new_scenes_comparisons"
INPUT = BASE / "city_street_000000026204_input.png"
ROWS = {
    "van_gogh": (OUT / "city_street_skill_vangogh_imagegen.png",
                 BASE / "city_street_000000026204_van_gogh_fp32.png",
                 BASE / "city_street_000000026204_van_gogh_int8.png"),
    "ukiyo_e": (OUT / "city_street_skill_ukiyoe_imagegen.png",
                BASE / "city_street_000000026204_ukiyo_e_fp32.png",
                BASE / "city_street_000000026204_ukiyo_e_int8.png"),
    "ink_landscape": (OUT / "city_street_skill_ink_imagegen.png",
                      BASE / "city_street_000000026204_ink_landscape_fp32.png",
                      BASE / "city_street_000000026204_ink_landscape_int8.png"),
}


def arr(path: Path) -> np.ndarray:
    im = ImageOps.fit(Image.open(path).convert("RGB"), (640, 480), Image.Resampling.LANCZOS)
    return np.asarray(im, dtype=np.float32)


def stats(a: np.ndarray) -> dict[str, float]:
    x = a / 255.0
    y = x.mean(axis=2)
    gx = np.diff(y, axis=1, prepend=y[:, :1])
    gy = np.diff(y, axis=0, prepend=y[:1, :])
    g = np.hypot(gx, gy)
    lap = np.diff(y, 2, axis=1, prepend=y[:, :1], append=y[:, -1:])
    lap += np.diff(y, 2, axis=0, prepend=y[:1, :], append=y[-1:, :])
    flat = np.mean(np.abs(np.diff(x, axis=1)) < (2.0 / 255.0))
    chroma = x.max(axis=2) - x.min(axis=2)
    theta = np.arctan2(gy, gx)
    weight = g + 1e-6
    coherence = abs(np.sum(weight * np.exp(2j * theta)) / np.sum(weight))
    return {
        "luma_mean_255": float(y.mean() * 255),
        "luma_std_255": float(y.std() * 255),
        "chroma_mean_255": float(chroma.mean() * 255),
        "dark_fraction_lt64": float((y < 64 / 255).mean()),
        "paper_fraction_gt220": float((y > 220 / 255).mean()),
        "gradient_mean_255": float(g.mean() * 255),
        "laplacian_std_255": float(lap.std() * 255),
        "flat_neighbor_fraction": float(flat),
        "orientation_coherence": float(coherence),
        "unique_rgb_64_bins": int(np.unique((a // 4).astype(np.uint8).reshape(-1, 3), axis=0).shape[0]),
    }


def psnr(a: np.ndarray, b: np.ndarray) -> float:
    mse = np.mean((a - b) ** 2)
    return float(10 * np.log10((255.0 ** 2) / max(mse, 1e-12)))


def main() -> None:
    result = {"input": str(INPUT.resolve()), "styles": {}}
    for style, (skill_path, fp32_path, int8_path) in ROWS.items():
        skill, fp32, int8 = map(arr, (skill_path, fp32_path, int8_path))
        result["styles"][style] = {
            "stats": {"skill": stats(skill), "stylecam_fp32": stats(fp32), "stylecam_int8": stats(int8)},
            "aligned_diagnostics": {
                "skill_vs_stylecam_fp32_psnr_db": psnr(skill, fp32),
                "skill_vs_stylecam_fp32_ssim": float(structural_similarity(skill, fp32, channel_axis=2, data_range=255)),
                "stylecam_int8_vs_fp32_psnr_db": psnr(int8, fp32),
                "stylecam_int8_vs_fp32_ssim": float(structural_similarity(int8, fp32, channel_axis=2, data_range=255)),
            },
        }
    path = OUT / "skill_network_gap_metrics.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(path.resolve())


if __name__ == "__main__":
    main()
