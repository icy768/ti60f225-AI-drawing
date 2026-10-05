# IN 轮换刷新收敛性（静止画面）：初始用固定统计量系数，每帧只统计并更新一层（按当前系数运行），
# 记录每帧输出与"逐帧 IN"输出的 PSNR，验证分时刷新收敛到逐帧 IN
import argparse
import os

import numpy as np

import golden
from eval import load_img
from export_blob import avg_stats
from train import ROOT, image_list


def run_with_coefs(q, img, coefs):
    # coefs[i] = (M, B) 或 None（无归一化层用自身系数）；返回输出与各层统计
    import torch
    import torch.nn.functional as F
    x = torch.from_numpy(np.ascontiguousarray(img)).permute(2, 0, 1)[None].double()
    feats, sts = [], []
    for i, L in enumerate(q["layers"]):
        acc = golden.conv_int(x, L)
        a = golden.shift_sat(acc, L["R"])
        sts.append(golden.stats(a) if coefs[i] is not None else None)
        M, B = coefs[i] if coefs[i] is not None else golden.coef_from_stats(L, None, 0)
        skip = feats[L["skip"]] if L["skip"] is not None else None
        x = golden.requant(a, L, M, B, skip)
        feats.append(x)
    y = F.pixel_shuffle(x, 2)[0].permute(1, 2, 0).to(torch.uint8).numpy()
    return y, sts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gen", default="rtl/gen/c24_gram_640x480")
    ap.add_argument("--style", type=int, default=1)
    ap.add_argument("--rounds", type=int, default=3)
    a = ap.parse_args()
    q = golden.load(os.path.join(ROOT, a.gen, "qparams"))
    train_files, ev = image_list()
    rnd = np.random.RandomState(0)
    cal = [load_img(train_files[i]) for i in rnd.choice(len(train_files), 6, replace=False)]
    fixed = avg_stats(q, cal, a.style)
    from PIL import Image
    img = np.asarray(Image.fromarray(load_img(ev[5])).resize((640, 480), Image.BILINEAR))
    y_dyn, _, _ = golden.run(q, img, a.style)
    in_layers = [i for i, L in enumerate(q["layers"]) if "gamma" in L]
    coefs = [golden.coef_from_stats(L, fixed[i], a.style) if i in in_layers else None
             for i, L in enumerate(q["layers"])]
    psnr = lambda y: 10 * np.log10(255 ** 2 / max(np.mean((y.astype(float) - y_dyn) ** 2), 1e-12))
    y, sts = run_with_coefs(q, img, coefs)
    print(f"第 0 帧（固定统计量）：对逐帧 IN 的 PSNR {psnr(y):.2f} dB")
    frame = 0
    for r in range(a.rounds):
        for li in in_layers:
            # 本帧按当前系数运行，统计 li 层，下一帧起生效
            y, sts = run_with_coefs(q, img, coefs)
            coefs[li] = golden.coef_from_stats(q["layers"][li], sts[li], a.style)
            frame += 1
        y, _ = run_with_coefs(q, img, coefs)
        print(f"第 {r + 1} 轮后（{frame} 帧）：PSNR {psnr(y):.2f} dB，逐位一致像素比例 {np.mean((y == y_dyn).all(-1)):.4f}")


if __name__ == "__main__":
    main()
