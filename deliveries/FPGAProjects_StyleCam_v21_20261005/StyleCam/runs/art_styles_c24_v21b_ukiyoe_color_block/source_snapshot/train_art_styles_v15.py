"""v15: restart from v6 with staged, style-specific supervision.

The deployed TinyStyleNet graph is unchanged.  Direction, signed-gradient,
regional ink, palette, and temporal terms are training-only objectives.
"""
import argparse
import hashlib
import json
import math
import random
import shutil
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from tinystyle import QCfg, TinyStyleNet, macs_per_pixel
from train import ROOT, CropSet, camera_domain_augment, image_list
from train_art_styles import gram
from train_art_styles_v4 import ArtFeatures, NAMES, reference_bank
from art_material_v7 import shift_consistency
from art_region_v10 import ink_loss, region_mean, source_regions, ukiyo_e_loss, van_gogh_loss
from art_spatial_priors import contours, luma, mean
from art_structure_v8 import covariance_loss, separated_loss, spatial_covariance, target


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sobel4(x):
    """Return 0, 90, 45 and 135 degree responses for a one-channel image."""
    k = x.new_tensor([
        [[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]],
        [[-1, -2, -1], [0, 0, 0], [1, 2, 1]],
        [[0, 1, 2], [-1, 0, 1], [-2, -1, 0]],
        [[2, 1, 0], [1, 0, -1], [0, -1, -2]],
    ]).unsqueeze(1) / 8
    x = F.pad(x, (1, 1, 1, 1), mode="reflect")
    return F.conv2d(x, k)


def direction_stats(x):
    e = sobel4(luma(x)).abs().mean((2, 3))
    return e / e.sum(1, keepdim=True).clamp_min(1e-6)


def rgb_stats(x):
    chroma = x.amax(1) - x.amin(1)
    mean_rgb = x.mean((2, 3))
    std_rgb = x.flatten(2).std(2, unbiased=False)
    chroma_mean = chroma.mean((1, 2), keepdim=False).unsqueeze(1)
    return torch.cat((mean_rgb, std_rgb, chroma_mean), 1)


def signed_gradient_loss(y, reference, mask):
    gy = sobel4(luma(y))[:, :2]
    gt = sobel4(luma(reference))[:, :2]
    aligned = torch.tanh(gy * 45) * torch.tanh(gt * 45)
    sign_penalty = F.relu(0.15 - aligned).mean(1, keepdim=True)
    magnitude = (gy.abs() - gt.abs()).abs().mean(1, keepdim=True)
    return region_mean(sign_penalty + 0.35 * magnitude, mask)


def interior_variance(y, mask):
    g = luma(y)
    local = (mean(g * g, 5) - mean(g, 5).square()).clamp_min(0).sqrt()
    return region_mean(F.relu(local - 0.010), mask)


def gradient_l1(a, b):
    ay, by = luma(a), luma(b)
    return (F.l1_loss(ay[:, :, 1:] - ay[:, :, :-1], by[:, :, 1:] - by[:, :, :-1]) +
            F.l1_loss(ay[:, :, :, 1:] - ay[:, :, :, :-1], by[:, :, :, 1:] - by[:, :, :, :-1]))


def save_checkpoint(out, name, net, opt, step, args, start):
    tmp = out / (name + ".tmp")
    torch.save(dict(
        cfg=net.cfg,
        styles=NAMES,
        sd={k: v.detach().cpu() for k, v in net.state_dict().items()},
        qat=False,
        it=step,
        opt=opt.state_dict(),
        args=vars(args),
        seconds=time.monotonic() - start,
        needs_new_calibration=True,
        board_validated=False,
        rng_python=random.getstate(),
        rng_numpy=np.random.get_state(),
        rng_torch=torch.get_rng_state(),
        rng_cuda=torch.cuda.get_rng_state_all(),
    ), tmp)
    tmp.replace(out / name)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--init", default="runs/art_styles_c24_graphic_v6/student.pt")
    p.add_argument("--out", required=True)
    p.add_argument("--steps", type=int, default=3000)
    p.add_argument("--batch", type=int, default=4)
    p.add_argument("--crop", type=int, default=256)
    p.add_argument("--lr", type=float, default=1.2e-4)
    p.add_argument("--seed", type=int, default=20261007)
    p.add_argument("--save-every", type=int, default=300)
    p.add_argument("--teacher-weight", type=float, default=0.16)
    p.add_argument("--temporal-weight", type=float, default=0.18)
    p.add_argument("--vg-direction-mult", type=float, default=1.0)
    p.add_argument("--ukiyo-flat-mult", type=float, default=1.0)
    p.add_argument("--ukiyo-edge-mult", type=float, default=1.0)
    p.add_argument("--ink-chroma-mult", type=float, default=1.0)
    p.add_argument("--phase-shift", type=float, default=0.0,
                   help="training-only shift of the staged style ramp; use 750 for a v15 continuation")
    args = p.parse_args()

    root = Path(ROOT)
    out = root / args.out
    if out.exists():
        raise FileExistsError(f"fresh output directory required: {out}")
    out.mkdir(parents=True)
    torch.set_num_threads(4)
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for v15")
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False

    ck = torch.load(root / args.init, map_location="cpu", weights_only=False)
    expected = dict(C=24, Fc=16, n_res=4, n_styles=3, norm="in", block="dw1")
    if ck["cfg"] != expected or ck["styles"] != NAMES:
        raise ValueError("v15 must start from the fixed three-style v6 graph")
    net = TinyStyleNet(**ck["cfg"]).cuda().train()
    net.load_state_dict(ck["sd"])
    teacher = TinyStyleNet(**ck["cfg"]).cuda().eval()
    teacher.load_state_dict(ck["sd"])
    teacher.requires_grad_(False)
    QCfg.enabled = QCfg.observe = False

    vgg = ArtFeatures().cuda().eval()
    refs = reference_bank(out, "cuda", args.crop, coarse_brush=True)
    ref_targets = []
    with torch.no_grad():
        for local in refs:
            features = [(vgg(x), weight, x) for x, weight in local]
            grams = [sum(weight * gram(fs[k]) for fs, weight, _ in features) for k in range(4)]
            covs = [sum(weight * spatial_covariance(fs[0])[k] for fs, weight, _ in features)
                    for k in range(5)]
            directions = sum(weight * direction_stats(x) for _, weight, x in features)
            colors = sum(weight * rgb_stats(x) for _, weight, x in features)
            ref_targets.append((grams, covs, directions, colors))

    train_files, held_files = image_list()
    if set(train_files) & set(held_files):
        raise ValueError("training and held-out images overlap")
    loader = torch.utils.data.DataLoader(
        CropSet(train_files, args.crop), batch_size=args.batch, shuffle=True,
        drop_last=True, num_workers=0)
    opt = torch.optim.Adam(net.parameters(), lr=args.lr)
    config = dict(
        args=vars(args),
        init_sha256=sha(root / args.init),
        cfg=ck["cfg"], styles=NAMES,
        params=sum(x.numel() for x in net.parameters()),
        conv_MACs_VGA=macs_per_pixel(net.specs)[0] * 640 * 480,
        graph_changed=False, quantization_validated=False, board_validated=False,
        training_note="v6 restart; staged regional direction, signed-gradient, flatness, ink and temporal supervision",
        reference_sha256=sha(out / "references.json"),
        train_files=[Path(f).name for f in train_files],
        development_files=[Path(f).name for f in held_files],
    )
    (out / "config.json").write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    snap = out / "source_snapshot"
    snap.mkdir()
    for name in ("train_art_styles_v15.py", "train.py", "tinystyle.py", "train_art_styles.py",
                 "train_art_styles_v4.py", "art_region_v10.py", "art_structure_v8.py",
                 "art_spatial_priors.py", "art_material_v7.py"):
        shutil.copy2(root / "algo" / name, snap / name)

    start = time.monotonic()
    step = 0
    window = []
    with (out / "train.jsonl").open("w", encoding="utf-8") as log:
        while step < args.steps:
            for xb in loader:
                si = step % len(NAMES)
                x = xb.cuda().float() / 255
                xa = camera_domain_augment(x * 255, 0.25) / 255
                style = torch.full((len(x),), si, device="cuda", dtype=torch.long)
                y = net(xa, style)
                with torch.no_grad():
                    fx = vgg(x)
                    baseline = teacher(xa, style)
                fy = vgg(y)
                grams, covs, dir_target, color_target = ref_targets[si]
                gram_loss = sum(
                    F.mse_loss(gram(f), g.expand(len(x), -1, -1)) /
                    g.square().mean().clamp_min(1e-8)
                    for f, g in zip(fy, grams)
                ) / 4
                content_loss = F.mse_loss(fy[2], fx[2]) / fx[2].square().mean().detach().clamp_min(1e-6)
                teacher_loss = F.l1_loss(y, baseline)
                grad_preserve = gradient_l1(y, baseline)
                chroma = (y.amax(1) - y.amin(1)).mean()
                tv = ((y[:, :, 1:] - y[:, :, :-1]).abs().mean() +
                      (y[:, :, :, 1:] - y[:, :, :, :-1]).abs().mean())
                phase = min(1.0, max(0.0, (step - 750 + args.phase_shift) / 750.0))
                late = min(1.0, max(0.0, (step - 1650) / 600.0))
                regional = source_regions(xa)
                interior, boundary, subject, paper = regional[4], regional[3], regional[5], regional[6]
                direct = gradient = tone = direction = flat = color = cov = edge = dry = temporal = y.new_zeros(())

                if si == 0:
                    extra = van_gogh_loss(y, xa)
                    direction = F.mse_loss(direction_stats(y), dir_target.expand(len(x), -1))
                    color = F.mse_loss(rgb_stats(y), color_target.expand(len(x), -1))
                    cov = covariance_loss(fy[0], covs)
                    edge = extra["edges"]
                    style_loss = (7.0 * extra["stroke"] + 3.0 * extra["continuity"] +
                                  4.0 * edge + 0.08 * args.vg_direction_mult * direction + 0.025 * color + 0.06 * cov)
                    loss = (1.0 * gram_loss + 0.18 * content_loss + args.teacher_weight * teacher_loss +
                            0.10 * grad_preserve + phase * style_loss + 0.005 * tv)
                elif si == 1:
                    t = target(xa, si)
                    direct, gradient, tone = separated_loss(y, t)
                    extra = ukiyo_e_loss(y, xa)
                    flat = interior_variance(y, interior)
                    signed = signed_gradient_loss(y, t, F.max_pool2d(boundary, 5, 1, 2))
                    edge = extra["outline"]
                    color = F.mse_loss(rgb_stats(y), color_target.expand(len(x), -1))
                    style_loss = (4.0 * args.ukiyo_flat_mult * extra["flat"] + 1.5 * extra["palette"] +
                                  8.0 * args.ukiyo_edge_mult * edge + 2.0 * extra["dark_line"] +
                                  1.5 * signed + 2.0 * flat + 0.025 * color)
                    loss = (1.0 * gram_loss + 0.18 * content_loss + args.teacher_weight * teacher_loss +
                            0.10 * grad_preserve + 0.35 * direct + 0.50 * gradient +
                            phase * style_loss + late * 0.02 * F.relu(chroma - 0.30) + 0.005 * tv)
                else:
                    t = target(xa, si)
                    direct, gradient, tone = separated_loss(y, t)
                    extra = ink_loss(y, xa)
                    high_y = y - mean(y, 2)
                    high_t = t - mean(t, 2)
                    edge_mask = torch.maximum(boundary, subject)
                    dry = region_mean((high_y - high_t).abs(), edge_mask)
                    ink_chroma = region_mean(y.amax(1, keepdim=True) - y.amin(1, keepdim=True), subject)
                    paper_floor = region_mean(F.relu(0.93 - luma(y)), paper)
                    tone_gap = F.relu(0.56 - (luma(y)[paper.bool()].mean() if paper.any() else y.new_tensor(0.56)) +
                                       luma(y)[subject.bool()].mean() if subject.any() else y.new_tensor(0.0))
                    style_loss = (2.5 * extra["dense"] + 3.0 * extra["paper"] +
                                  5.0 * extra["strong_edge"] + 1.5 * extra["fade"] +
                                  0.04 * args.ink_chroma_mult * ink_chroma + 0.20 * dry + 0.50 * paper_floor)
                    loss = (1.0 * gram_loss + 0.18 * content_loss + args.teacher_weight * teacher_loss +
                            0.10 * grad_preserve + 0.25 * direct + 0.35 * gradient +
                            phase * style_loss + 0.04 * tone + 0.005 * tv)

                if step % 4 == 0:
                    temporal = shift_consistency(net, xa, style, y, step)
                    loss = loss + args.temporal_weight * temporal
                if not torch.isfinite(loss):
                    raise RuntimeError(f"nonfinite loss at step {step}")
                lr = args.lr * (0.25 + 0.75 * 0.5 * (1 + math.cos(math.pi * step / args.steps)))
                for group in opt.param_groups:
                    group["lr"] = lr
                opt.zero_grad(set_to_none=True)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(net.parameters(), 1.0, error_if_nonfinite=True)
                opt.step()
                step += 1
                window.append(dict(style=NAMES[si], loss=float(loss), gram=float(gram_loss),
                                   content=float(content_loss), teacher=float(teacher_loss),
                                   direction=float(direction), flat=float(flat), color=float(color),
                                   dry=float(dry), temporal=float(temporal), phase=phase))
                if step % 150 == 0 or step == args.steps:
                    means = {}
                    for name in NAMES:
                        rows = [r for r in window if r["style"] == name]
                        if rows:
                            means[name] = {k: float(np.mean([r[k] for r in rows]))
                                           for k in ("loss", "gram", "content", "teacher", "direction", "flat", "color", "dry", "temporal")}
                    row = dict(step=step, seconds=time.monotonic() - start, lr=lr,
                               phase=phase, losses=means,
                               peak_cuda_mb=torch.cuda.max_memory_allocated() / 2**20)
                    log.write(json.dumps(row) + "\n")
                    log.flush()
                    print(json.dumps(row), flush=True)
                    window = []
                if step % args.save_every == 0 or step == args.steps:
                    save_checkpoint(out, f"step_{step:05}.pt", net, opt, step, args, start)
                if step >= args.steps:
                    break
    save_checkpoint(out, "student.pt", net, opt, step, args, start)
    print("SAVED", out, flush=True)


if __name__ == "__main__":
    main()
