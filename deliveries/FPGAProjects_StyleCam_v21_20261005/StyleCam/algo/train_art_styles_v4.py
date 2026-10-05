"""Texture-first art training. All extra operators are offline losses only."""
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
from PIL import Image, ImageEnhance, ImageOps
from torchvision.models import VGG16_Weights, vgg16

from tinystyle import QCfg, TinyStyleNet
from train import ROOT, CropSet, camera_domain_augment, image_list
from train_art_styles import gram

NAMES = ["van_gogh", "ukiyo_e", "ink_landscape"]
# Bounds are fractions of the original work, excluding mounts and inscriptions.
REFERENCES = {
    "van_gogh": [(436535, .60, (0.03, .03, .97, .97)),
                 (436524, .25, (0.03, .03, .97, .97)),
                 (437998, .15, (0.03, .03, .97, .97))],
    "ukiyo_e": [(39799, .70, (.04, .06, .96, .96)),
                (36492, .20, (.04, .08, .96, .96)),
                (45287, .10, (.04, .08, .96, .96))],
    "ink_landscape": [(45636, .55, (.10, .32, .90, .88)),
                      (49173, .25, (.08, .15, .90, .90)),
                      (49180, .20, (.08, .26, .90, .86))],
}


class ArtFeatures(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.features = vgg16(weights=VGG16_Weights.IMAGENET1K_V1).features[:23].eval()
        self.features.requires_grad_(False)
        self.register_buffer("mean", torch.tensor([.485, .456, .406])[None, :, None, None])
        self.register_buffer("std", torch.tensor([.229, .224, .225])[None, :, None, None])

    def forward(self, x):
        x = (x - self.mean) / self.std
        result = []
        for i, layer in enumerate(self.features):
            x = layer(x)
            if i in (3, 8, 15, 22):
                # Clone because the next VGG ReLU uses inplace=True.
                result.append(x.clone())
        return result


def luminance(x):
    return x[:, :1] * .299 + x[:, 1:2] * .587 + x[:, 2:3] * .114


def blur(x, radius=2):
    return F.avg_pool2d(F.pad(x, (radius,) * 4, mode="reflect"), radius * 2 + 1, 1)


def edge(x):
    g = luminance(x)
    k = x.new_tensor([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]]).view(1, 1, 3, 3) / 8
    g = F.pad(g, (1,) * 4, mode="reflect")
    return (F.conv2d(g, k).square() + F.conv2d(g, k.transpose(2, 3)).square() + 1e-8).sqrt()


def spatial_prior(x, si, strong=False):
    """A weak spatial prior, not the sole style target or inference filter."""
    sm = blur(blur(x, 2), 2)
    ed = edge(sm)
    if si == 1:
        palette = x.new_tensor([[.08, .14, .22], [.12, .30, .45], [.30, .46, .55],
                                [.73, .79, .76], [.94, .87, .70], [.72, .33, .24],
                                [.43, .49, .30], [.77, .62, .37]])
        distances = (sm[:, None] - palette[None, :, :, None, None]).square().sum(2)
        flat = palette[distances.argmin(1)].permute(0, 3, 1, 2)
        line = ((ed - .025) / .07).clamp(0, 1)
        return flat * (1 - .8 * line)
    g = luminance(sm)
    if strong:
        # Five washes with smooth transitions, bright negative space, and
        # structure-dependent ink contours. No artificial random paper noise.
        wash = (.10 + 1.22 * g.pow(.42)).clamp(0, 1)
        line = ((ed - .015) / .085).clamp(0, 1)
        return (wash * (1 - .90 * line)).repeat(1, 3, 1, 1)
    # Preserve tonal wash in shadows while leaving light regions near paper white.
    wash = (.12 + 1.16 * g.pow(.55)).clamp(0, 1)
    line = ((ed - .025) / .09).clamp(0, 1)
    return (wash * (1 - .85 * line)).repeat(1, 3, 1, 1)


def reference_bank(out, device, size, coarse_brush=False):
    root = Path(ROOT)
    dataset = root / "dataset_v2"
    records = {int(r["object_id"]): r for r in
               map(json.loads, (dataset / "manifests/met_candidates.jsonl").read_text(encoding="utf-8").splitlines())}
    roles = {int(r["object_id"]): r.get("candidate_role") for r in
             map(json.loads, (dataset / "manifests/met_candidates_organized.jsonl").read_text(encoding="utf-8").splitlines())}
    previous = {int(r["met_id"]): r for r in
                json.loads((root / "data/styles_art/provenance.json").read_text(encoding="utf-8"))}
    metadata, tensors = [], []
    (out / "references").mkdir(exist_ok=True)
    for si, name in enumerate(NAMES):
        local = []
        for oid, weight, bounds in REFERENCES[name]:
            if roles.get(oid) == "holdout":
                raise ValueError(f"Artwork {oid} is reserved for holdout")
            if oid in previous:
                rec = previous[oid]
                path = root / "data/styles_art" / rec["file"]
                url = rec["url"]
            else:
                rec = records[oid]
                path = dataset / rec["path"]
                url = rec["primary_image"]
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != rec["sha256"]:
                raise ValueError(f"Reference hash mismatch: {path}")
            im = Image.open(path).convert("RGB")
            w, h = im.size
            im = im.crop(tuple(round(v * (w if j % 2 == 0 else h)) for j, v in enumerate(bounds)))
            if si == 0:
                if coarse_brush:
                    # Enlarged pigment marks in the target, not a generated
                    # screen-fixed texture. Keep original crop metadata below.
                    w, h = im.size
                    im = im.crop((int(w*.25), int(h*.25), int(w*.75), int(h*.75)))
                im = ImageEnhance.Color(im).enhance(1.35)
                im = ImageEnhance.Contrast(im).enhance(1.08)
            elif si == 1:
                im = ImageEnhance.Color(im).enhance(1.20)
            else:
                im = ImageOps.autocontrast(im.convert("L"), cutoff=1).convert("RGB")
            im = ImageOps.fit(im, (size, size), Image.Resampling.LANCZOS)
            im.save(out / "references" / f"{name}_{oid}.png")
            x = torch.from_numpy(np.asarray(im).copy()).permute(2, 0, 1)[None].to(device).float() / 255
            local.append((x, weight))
            metadata.append(dict(style=name, object_id=oid, weight=weight, crop=bounds,
                                 additional_center_crop_fraction=.5 if si == 0 and coarse_brush else 1.0,
                                 source=str(path), url=url, sha256=actual, title=rec["title"],
                                 transform="color 1.35 contrast 1.08" if si == 0 else
                                 "color 1.20" if si == 1 else "grayscale autocontrast cutoff 1 percent"))
        tensors.append(local)
    (out / "references.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return tensors


def save(path, net, opt, step, args, seconds):
    temp = path.with_suffix(".tmp")
    torch.save(dict(cfg=net.cfg, styles=NAMES, sd=net.state_dict(), qat=False,
                    it=step, opt=opt.state_dict(), args=vars(args), seconds=seconds,
                    rng_python=random.getstate(), rng_numpy=np.random.get_state(),
                    rng_torch=torch.get_rng_state(), rng_cuda=torch.cuda.get_rng_state_all(),
                    style_training="v4 four-scale relative Gram + selected artwork palette + weak spatial priors"), temp)
    temp.replace(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--init", default="runs/art_styles_c24_strong_v3/student.pt")
    ap.add_argument("--out", default="runs/art_styles_c24_texture_v4")
    ap.add_argument("--steps", type=int, default=2400)
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--crop", type=int, default=256)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--content", type=float, default=.12)
    ap.add_argument("--style", type=float, default=1.0)
    ap.add_argument("--prior", type=float, default=.15)
    ap.add_argument("--save_every", type=int, default=600)
    ap.add_argument("--seed", type=int, default=20261004)
    ap.add_argument("--differentiated", action="store_true")
    ap.add_argument("--graphic", action="store_true")
    args = ap.parse_args()
    torch.set_num_threads(4)
    random.seed(args.seed); np.random.seed(args.seed); torch.manual_seed(args.seed)
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA unavailable; refusing an unexpectedly long CPU run")
    dev = "cuda"
    out = Path(ROOT) / args.out
    if (out / "student.pt").exists():
        raise FileExistsError(f"Use a fresh output directory: {out}")
    out.mkdir(parents=True, exist_ok=True)
    snapshot = out / "source_snapshot"
    snapshot.mkdir(exist_ok=True)
    for filename in ("train_art_styles_v4.py", "tinystyle.py", "train.py", "train_art_styles.py", "art_spatial_priors.py"):
        shutil.copy2(Path(__file__).parent / filename, snapshot / filename)
    ck = torch.load(Path(ROOT) / args.init, map_location="cpu", weights_only=False)
    expected = dict(C=24, Fc=16, n_res=4, n_styles=3, norm="in", block="dw1")
    assert ck["cfg"] == expected and ck["styles"] == NAMES
    net = TinyStyleNet(**ck["cfg"]).to(dev)
    net.load_state_dict(ck["sd"]); net.train()
    QCfg.enabled = False; QCfg.observe = False
    vgg = ArtFeatures().to(dev).eval()
    refs = reference_bank(out, dev, args.crop, coarse_brush=args.differentiated)
    targets = []
    with torch.no_grad():
        for local in refs:
            features = [(vgg(x), weight, x) for x, weight in local]
            gs = [sum(weight * gram(fs[i]) for fs, weight, _ in features) for i in range(4)]
            # Fixed target instead of contradictory randomly selected references each step.
            color = sum(weight * x.mean((2, 3)) for _, weight, x in features)
            targets.append((gs, color))
    train_files, eval_files = image_list()
    assert not set(train_files).intersection(eval_files)
    dl = torch.utils.data.DataLoader(CropSet(train_files, args.crop), batch_size=args.batch,
                                    shuffle=True, drop_last=True, num_workers=0)
    opt = torch.optim.Adam(net.parameters(), lr=args.lr)
    (out / "config.json").write_text(json.dumps(dict(args=vars(args), cfg=net.cfg,
        train_images=len(train_files), evaluation_images=len(eval_files),
        init_sha256=hashlib.sha256((Path(ROOT) / args.init).read_bytes()).hexdigest(),
        inference_graph_changed=False, quantization_validated=False), indent=2), encoding="utf-8")
    step = 0; started = time.monotonic(); logs = []
    with (out / "train.jsonl").open("w", encoding="utf-8") as log:
        while step < args.steps:
            for xb in dl:
                si = step % 3
                x = xb.to(dev).float() / 255
                xa = camera_domain_augment(x * 255, .30) / 255
                st = torch.full((len(x),), si, dtype=torch.long, device=dev)
                y = net(xa, st)
                with torch.no_grad():
                    fx = vgg(x)
                fy = vgg(y)
                gs, color = targets[si]
                ls = sum(F.mse_loss(gram(f), g.expand(len(x), -1, -1)) /
                         g.square().mean().clamp_min(1e-8) for f, g in zip(fy, gs)) / 4
                lc = F.mse_loss(fy[2], fx[2]) / fx[2].square().mean().detach().clamp_min(1e-6)
                palette = F.mse_loss(y.mean((2, 3)), color.expand(len(x), -1))
                prior = y.new_zeros(()) if si == 0 else F.l1_loss(blur(y), spatial_prior(x, si))
                chroma = (y - y.mean(1, keepdim=True)).square().mean() if si == 2 else y.new_zeros(())
                tv = (y[:, :, 1:] - y[:, :, :-1]).abs().mean() + (y[:, :, :, 1:] - y[:, :, :, :-1]).abs().mean()
                loss = args.style * ls + args.content * lc + .5 * palette + args.prior * prior + 6 * chroma + .01 * tv
                if args.differentiated:
                    if si == 0:
                        # Coarser reference texture needs less pixel smoothing.
                        loss = 1.4 * ls + .11 * lc + .6 * palette + .015 * tv
                    else:
                        target = spatial_prior(x, si, strong=True)
                        direct = F.l1_loss(y, target)
                        line_loss = F.l1_loss(edge(y), edge(target))
                        # Penalize texture away from actual content boundaries.
                        flat = (1 - edge(blur(x))/.04).clamp(0, 1).detach()
                        grain = ((y - blur(y)).abs() * flat).mean()
                        if si == 1:
                            loss = .14 * ls + .08 * lc + 2.5 * direct + 2 * line_loss + 4 * grain + .06 * tv
                        else:
                            loss = .12 * ls + .07 * lc + 3 * direct + 2 * line_loss + 4 * grain + 18 * chroma + .05 * tv
                if args.graphic and si != 0:
                    from art_spatial_priors import target as graphic_target, palette_distance
                    target = graphic_target(x, si)
                    direct = F.l1_loss(y, target)
                    line_loss = F.l1_loss(edge(y), edge(target))
                    flat = (1-edge(blur(x))/.04).clamp(0, 1).detach()
                    grain = ((y-blur(y)).abs()*flat).mean()
                    if si == 1:
                        loss = .10*ls+.07*lc+3*direct+3*line_loss+1.2*grain+.5*palette_distance(y, x)+.02*tv
                    else:
                        loss = .10*ls+.07*lc+3*direct+3*line_loss+1.2*grain+20*chroma+.02*tv
                if not torch.isfinite(loss):
                    raise RuntimeError(f"Nonfinite loss at {step}")
                lr = args.lr * (.2 + .8 * .5 * (1 + math.cos(math.pi * step / args.steps)))
                for group in opt.param_groups:
                    group["lr"] = lr
                opt.zero_grad(set_to_none=True); loss.backward()
                torch.nn.utils.clip_grad_norm_(net.parameters(), 5.0); opt.step()
                step += 1
                logs.append(dict(style=NAMES[si], loss=float(loss), gram=float(ls), content=float(lc),
                                 palette=float(palette), prior=float(prior), chroma=float(chroma)))
                if step % 150 == 0 or step == args.steps:
                    per_style = {name: {k: float(np.mean([r[k] for r in logs if r["style"] == name]))
                                       for k in ("loss", "gram", "content", "prior", "chroma")}
                                 for name in NAMES if any(r["style"] == name for r in logs)}
                    row = dict(step=step, seconds=time.monotonic()-started, lr=lr, losses=per_style,
                               peak_cuda_mb=torch.cuda.max_memory_allocated()/2**20)
                    line = json.dumps(row); log.write(line + "\n"); log.flush(); print(line, flush=True); logs = []
                if step % args.save_every == 0 or step == args.steps:
                    save(out / f"step_{step:05d}.pt", net, opt, step, args, time.monotonic()-started)
                if step >= args.steps:
                    break
    save(out / "student.pt", net, opt, step, args, time.monotonic()-started)
    print(f"SAVED {out / 'student.pt'}", flush=True)


if __name__ == "__main__":
    main()
