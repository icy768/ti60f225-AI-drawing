# 评估：学生网络 vs 教师网络的 PSNR/SSIM（全分辨率保留集），并输出对比拼图
import argparse
import json
import os
import time

import numpy as np
import torch
from PIL import Image
from skimage.metrics import peak_signal_noise_ratio, structural_similarity

from teacher import load_teacher, teacher_macs_per_pixel
from tinystyle import QCfg, TinyStyleNet, macs_per_pixel, param_count
from train import DATA, ROOT, image_list


def load_student(path, dev):
    ck = torch.load(path, map_location="cpu", weights_only=False)
    net = TinyStyleNet(**ck["cfg"])
    net.load_state_dict(ck["sd"])
    QCfg.enabled = ck["qat"]
    QCfg.observe = False
    return net.to(dev).eval(), ck["styles"]


def load_img(path):
    im = np.asarray(Image.open(path).convert("RGB"))
    h, w = im.shape[0] // 4 * 4, im.shape[1] // 4 * 4
    return im[:h, :w]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="runs/default")
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--grid", type=int, default=4)
    a = ap.parse_args()
    dev = "cuda"
    run = os.path.join(ROOT, a.run)
    net, styles = load_student(os.path.join(run, "student.pt"), dev)
    teachers = [load_teacher(os.path.join(DATA, "saved_models", f"{s}.pth"), dev) for s in styles]
    _, files = image_list()
    files = files[: a.n]

    res = {s: [[], []] for s in styles}
    rows = []
    with torch.no_grad():
        for i, f in enumerate(files):
            im = load_img(f)
            x = torch.from_numpy(im).permute(2, 0, 1)[None].float().to(dev)
            row = [im]
            for si, s in enumerate(styles):
                t = teachers[si](x).clamp(0, 255).round()[0].permute(1, 2, 0).byte().cpu().numpy()
                st = torch.full((1,), si, dtype=torch.long, device=dev)
                y = (net(x / 255.0, st).clamp(0, 1) * 255).round()[0].permute(1, 2, 0).byte().cpu().numpy()
                res[s][0].append(peak_signal_noise_ratio(t, y, data_range=255))
                res[s][1].append(structural_similarity(t, y, channel_axis=2, data_range=255))
                if i < a.grid:
                    row += [t, y]
            if i < a.grid:
                rows.append(np.concatenate([np.asarray(Image.fromarray(r).resize((320, 240))) for r in row], 1))

    macs, _ = macs_per_pixel(net.specs)
    w, aff, b = param_count(net.specs, len(styles))
    summary = dict(
        run=a.run, qat=QCfg.enabled, n_images=len(files),
        student_macs_per_px=round(macs), teacher_macs_per_px=round(teacher_macs_per_pixel()),
        student_params=w + aff + b, teacher_params=sum(p.numel() for p in teachers[0].parameters()),
        per_style={s: dict(psnr=round(float(np.mean(v[0])), 2), ssim=round(float(np.mean(v[1])), 4))
                   for s, v in res.items()},
    )
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    json.dump(summary, open(os.path.join(run, "eval.json"), "w"), ensure_ascii=False, indent=1)
    if rows:
        Image.fromarray(np.concatenate(rows, 0)).save(os.path.join(run, "compare.jpg"), quality=90)


if __name__ == "__main__":
    main()
