"""Fit deterministic style signals on one training crop.

This is a decoder capacity control only.  It does not optimize the fixed17
set, use real-art references, or provide a student quality/generalization
claim.  The signals are deliberately simple and spatially structured:
directional multiscale strokes, quantized flat regions with contours, and
grayscale wash with paper reserve.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import random
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
import torch
from torch import nn
from torch.nn import functional as F

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
from model_v4_replicate import ReplicateV4
from model_v4_subpixel import SubpixelV4
from model_v4_subpixel_lite import SubpixelLiteV4
from style_pilot_v4 import parameter_storage

STYLES = ("vangogh", "ukiyoe", "ink")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_crop(path: Path, size=(256, 320)) -> torch.Tensor:
    a = np.array(Image.open(path).convert("RGB"), copy=True)
    h, w = a.shape[:2]
    th, tw = size
    y0, x0 = max(0, (h - th) // 2), max(0, (w - tw) // 2)
    a = a[y0:y0 + th, x0:x0 + tw]
    return torch.from_numpy(a).permute(2, 0, 1)[None].float().cuda() / 255.0


def rgb(x: torch.Tensor) -> Image.Image:
    a = (x.detach()[0].clamp(0, 1).permute(1, 2, 0).cpu().numpy() * 255).round().astype(np.uint8)
    return Image.fromarray(a)


def blur(x: torch.Tensor, k: int) -> torch.Tensor:
    return F.avg_pool2d(F.pad(x, (k // 2,) * 4, mode="replicate"), k, 1)


def targets(x: torch.Tensor) -> list[torch.Tensor]:
    """Return non-reference deterministic signals with preserved composition."""
    b, _, h, w = x.shape
    yy, xx = torch.meshgrid(
        torch.linspace(-1, 1, h, device=x.device),
        torch.linspace(-1, 1, w, device=x.device), indexing="ij")
    lum = (x * x.new_tensor([.299, .587, .114]).view(1, 3, 1, 1)).sum(1, keepdim=True)
    gx = lum[..., :, 1:] - lum[..., :, :-1]
    gy = lum[..., 1:, :] - lum[..., :-1, :]
    grad = F.pad(gx.abs(), (0, 1, 0, 0)) + F.pad(gy.abs(), (0, 0, 0, 1))
    edge = (grad / (grad.mean(dim=(-2, -1), keepdim=True) + 1e-4)).clamp(0, 3)

    # Van Gogh control: long and short strokes at two orientations with
    # spatially varying amplitude, added to a low-frequency color anchor.
    field_a = torch.sin(15.0 * (0.80 * xx + 0.35 * yy) + 1.8 * torch.sin(3 * yy))
    field_b = torch.sin(31.0 * (-0.25 * xx + 0.95 * yy) + 1.2 * torch.sin(2 * xx))
    strokes = (0.035 * field_a + 0.018 * field_b)[None, None]
    vg = blur(x, 9) + strokes * (0.35 + 0.8 * edge) * x.new_tensor([1.0, .72, .52]).view(1, 3, 1, 1)
    vg = (vg + 0.045 * torch.sin(7 * xx + 4 * yy)[None, None]).clamp(0, 1)

    # Ukiyo-e control: region quantization plus a continuous, low-density
    # contour.  The contour is derived from the input geometry only.
    flat = torch.round(blur(x, 9) * 5) / 5
    contour = (edge > 0.80).float()
    ink_line = (0.15 * contour).expand(-1, 3, -1, -1)
    uk = (flat * 0.96 + x.new_tensor([.04, .02, .00]).view(1, 3, 1, 1) - ink_line).clamp(0, 1)

    # Ink control: neutral luminance, multiscale wash, dark sparse marks and
    # a deliberate paper reserve.  The paper reserve is not mere clipping.
    wash = blur(lum, 17) * (0.80 + 0.16 * torch.sin(2.5 * xx + .8 * yy)[None, None])
    dark = (edge > 1.35).float() * 0.28
    paper = (lum > lum.mean(dim=(-2, -1), keepdim=True) + .18).float()
    ink = (wash - dark + 0.10 * paper).repeat(1, 3, 1, 1).clamp(0, 1)
    return [vg, uk, ink]


def metrics(y: torch.Tensor, t: torch.Tensor, source: torch.Tensor) -> dict:
    yp, tp = y - blur(y, 5), t - blur(t, 5)
    return {
        "MAE": float((y - t).abs().mean()),
        "highpass_MAE": float((yp - tp).abs().mean()),
        "highpass_cosine": float(F.cosine_similarity(yp.flatten(1), tp.flatten(1), dim=1).mean()),
        "input_MAE": float((y - source).abs().mean()),
        "saturation_fraction": float(((y < .01) | (y > .99)).float().mean()),
    }


def macs(model: nn.Module, style: int, shape=(1, 3, 256, 320)) -> int:
    count = 0
    hooks = []
    def hook(module, _inp, out):
        nonlocal count
        count += out.numel() * module.weight[0].numel()
    for m in model.modules():
        if isinstance(m, nn.Conv2d):
            hooks.append(m.register_forward_hook(hook))
    with torch.no_grad():
        model(torch.zeros(*shape, device="cuda"), style)
    for h in hooks:
        h.remove()
    return count


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="decoder_signal_fit_01")
    ap.add_argument("--updates-per-style", type=int, default=600)
    ap.add_argument("--models", nargs="+", choices=("A64_replicate", "subpixel", "subpixel_lite"),
                    default=["A64_replicate", "subpixel_lite"])
    args = ap.parse_args()
    out = ROOT / "reports" / args.run
    out.mkdir(exist_ok=False)
    torch.manual_seed(20261024); np.random.seed(20261024); random.seed(20261024)
    torch.backends.cudnn.benchmark = True
    source_path = ROOT / "reports" / "distribution_reachability_05" / "000000002153_INPUT_TRAINING.png"
    source = load_crop(source_path)
    target_list = targets(source)
    rgb(source).save(out / "INPUT_TRAINING_CROP.png")
    for style, target in zip(STYLES, target_list):
        rgb(target).save(out / f"TARGET_{style}_CONTROL_SIGNAL.png")
    cfg = {
        "kind": "decoder capacity control only; not student quality/generalization evidence",
        "time": dt.datetime.now().astimezone().isoformat(),
        "updates_per_style": args.updates_per_style, "crop": [256, 320],
        "source": str(source_path.relative_to(ROOT)), "source_sha256": sha(source_path),
        "targets": "deterministic directional strokes / quantized regions+contour / neutral wash+paper reserve",
        "seed": 20261024, "optimizer": "Adam lr=8e-4, L1 + 2*highpass-L1, gradclip=3",
        "models": {}, "promoted": False, "actual_integer_export": False,
        "actual_FPGA_resources": None, "actual_board_FPS": None,
    }
    (out / "config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    log = (out / "metrics.jsonl").open("w", buffering=1, encoding="utf-8")
    constructors = {
        "A64_replicate": lambda: ReplicateV4(detail_scale=.35, residual_scale=.65),
        "subpixel": lambda: SubpixelV4(residual_scale=.65),
        "subpixel_lite": lambda: SubpixelLiteV4(residual_scale=.65),
    }
    for name in args.models:
        torch.manual_seed(20261024); random.seed(20261024); np.random.seed(20261024)
        model = constructors[name]().cuda().train()
        cfg["models"][name] = {"VGA_conv_MAC_256x320": [macs(model, i) for i in range(3)], **parameter_storage(model),
                                "actual_integer_export": False, "actual_FPGA_resources": None, "actual_board_FPS": None}
        (out / "config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        opt = torch.optim.Adam(model.parameters(), lr=8e-4, betas=(.9, .99))
        start = time.time()
        for step in range(1, args.updates_per_style * 3 + 1):
            si = (step - 1) % 3
            opt.zero_grad(set_to_none=True)
            y = model(source, si)
            t = target_list[si]
            hp_y, hp_t = y - blur(y, 5), t - blur(t, 5)
            loss = (y - t).abs().mean() + 2.0 * (hp_y - hp_t).abs().mean()
            if not torch.isfinite(loss):
                raise FloatingPointError((name, step, float(loss)))
            loss.backward()
            norm = torch.nn.utils.clip_grad_norm_(model.parameters(), 3., error_if_nonfinite=True)
            opt.step()
            if step in (1, 2, 3) or step % 300 == 0:
                row = {"model": name, "step": step, "style": STYLES[si], "loss": float(loss.detach()),
                       "gradnorm": float(norm), **metrics(y.detach(), t, source), "seconds": time.time() - start}
                log.write(json.dumps(row) + "\n"); print("DECODER_SIGNAL", json.dumps(row), flush=True)
        model.eval(); result = {}
        with torch.no_grad():
            for si, style in enumerate(STYLES):
                y = model(source, si); result[style] = metrics(y, target_list[si], source)
                rgb(y).save(out / f"{name}_{style}_FIT.png")
        cfg["models"][name]["fits"] = result
        (out / f"{name}_result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        del model, opt; torch.cuda.empty_cache()
    sheet = Image.new("RGB", ((2 + len(args.models)) * 320, 3 * 286), "white")
    draw = ImageDraw.Draw(sheet)
    for si, style in enumerate(STYLES):
        ims = [rgb(source), Image.open(out / f"TARGET_{style}_CONTROL_SIGNAL.png")]
        ims += [Image.open(out / f"{m}_{style}_FIT.png") for m in args.models]
        labels = ["INPUT", "CONTROL TARGET"] + [m + " FIT" for m in args.models]
        for col, (im, label) in enumerate(zip(ims, labels)):
            sheet.paste(im.resize((320, 256)), (col * 320, si * 286))
            draw.text((col * 320 + 2, si * 286 + 258), style + " " + label, fill="black")
    sheet.save(out / "CONTROL_SIGNAL_FITS_NOT_GENERALIZATION.jpg", quality=96)
    cfg["finished"] = dt.datetime.now().astimezone().isoformat()
    (out / "config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    (out / "finished.json").write_text(json.dumps({"promoted": False, "time": cfg["finished"]}, indent=2), encoding="utf-8")
    print("DECODER_SIGNAL_FINISHED_NO_PROMOTION", flush=True)


if __name__ == "__main__":
    main()
