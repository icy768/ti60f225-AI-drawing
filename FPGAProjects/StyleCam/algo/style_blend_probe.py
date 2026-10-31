# 风格插值离线验证：卷积权重各风格共享，只在条件归一化里把两种风格的 gamma/beta 线性混合
#   (1-a)*A + a*B，a 取 0~1。输出每对风格的过渡拼图，以及相邻 a 之间的平均像素变化（看是否平滑、无突跳）。
#   硬件 IN 系数 M = gamma/sigma、B = beta - gamma*mu/sigma 对 gamma/beta 是线性的，固件写混合值即可复现。
#   只用 CPU，不占训练用的显卡。
import argparse
import json
import os

import numpy as np
import torch
from PIL import Image, ImageDraw, ImageOps

from tinystyle import QCfg, TinyStyleNet
from train import ROOT, image_list


def load_student(path, dev):   # 同 eval.py（避免引入 skimage 依赖）
    ck = torch.load(path, map_location="cpu", weights_only=False)
    net = TinyStyleNet(**ck["cfg"])
    net.load_state_dict(ck["sd"])
    QCfg.enabled = ck["qat"]
    QCfg.observe = False
    return net.to(dev).eval(), ck["styles"]


def load_img(path):
    im = np.asarray(Image.open(path).convert("RGB"))
    return im[: im.shape[0] // 4 * 4, : im.shape[1] // 4 * 4]


def run(net, img, style):
    x = torch.from_numpy(img).permute(2, 0, 1)[None].float() / 255
    with torch.no_grad():
        y = net(x, torch.tensor([style]))
    return (y[0].clamp(0, 1).permute(1, 2, 0).numpy() * 255 + 0.5).astype(np.uint8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="runs/art_styles_c24_v21b_ukiyoe_qat900_soft15")
    ap.add_argument("--out", default="runs/style_blend_probe_20261031")
    ap.add_argument("--n", type=int, default=4)
    ap.add_argument("--steps", type=int, default=5)
    ap.add_argument("--threads", type=int, default=4)
    a = ap.parse_args()
    torch.set_num_threads(a.threads)
    out = os.path.join(ROOT, a.out)
    os.makedirs(out, exist_ok=True)
    net, styles = load_student(os.path.join(ROOT, a.run, "student.pt"), "cpu")
    norms = [L.norm for L in net.layers if L.norm is not None]
    orig = [(n.gamma.data.clone(), n.beta.data.clone()) for n in norms]
    _, files = image_list()
    rnd = np.random.RandomState(1)
    imgs = [np.asarray(ImageOps.fit(Image.fromarray(load_img(files[i])), (640, 480)))
            for i in rnd.choice(len(files), a.n, replace=False)]
    alphas = np.linspace(0, 1, a.steps)
    report = {}
    for sa, sb in [(0, 1), (1, 2), (0, 2)]:
        name = f"{styles[sa]}_to_{styles[sb]}"
        rows, deltas = [], []
        for img in imgs:
            outs = []
            for al in alphas:
                for n, (g, b) in zip(norms, orig):      # 槽 sa 写入混合值，其余槽不动
                    n.gamma.data[sa] = (1 - al) * g[sa] + al * g[sb]
                    n.beta.data[sa] = (1 - al) * b[sa] + al * b[sb]
                outs.append(run(net, img, sa))
            for n, (g, b) in zip(norms, orig):
                n.gamma.data.copy_(g)
                n.beta.data.copy_(b)
            # 端点必须与原风格完全一致
            assert np.array_equal(outs[0], run(net, img, sa)) and np.array_equal(outs[-1], run(net, img, sb))
            deltas.append([float(np.abs(outs[k + 1].astype(int) - outs[k]).mean()) for k in range(len(outs) - 1)])
            rows.append(np.concatenate([img] + outs, axis=1))
        grid = Image.fromarray(np.concatenate(rows, axis=0)).resize((rows[0].shape[1] // 2, len(rows) * 240))
        d = ImageDraw.Draw(grid)
        for k, lab in enumerate(["input"] + [f"a={al:.2f}" for al in alphas]):
            d.text((k * 320 + 6, 4), lab, fill=(255, 255, 0))
        grid.save(os.path.join(out, name + ".jpg"), quality=90)
        mean = np.mean(deltas, axis=0).round(2).tolist()
        report[name] = {"step_mean_abs_change": mean, "max_over_min": round(max(mean) / max(min(mean), 1e-6), 2)}
        print(name, report[name], flush=True)
    with open(os.path.join(out, "report.json"), "w", encoding="utf-8") as f:
        json.dump({"run": a.run, "alphas": alphas.tolist(), "pairs": report}, f, indent=2)



def integer_check(contract="audits/v21b_ukiyoe_qat900_soft15_export", n=4, steps=5):
    """硬件整数路径（golden，逐位等同板上）：混合 gamma/beta 后 M/B 是否饱和、过渡是否仍平滑。"""
    import golden
    q = golden.load(os.path.join(ROOT, contract))
    orig = [(L["gamma"].copy(), L["beta"].copy()) if "gamma" in L else None for L in q["layers"]]
    _, files = image_list()
    rnd = np.random.RandomState(1)
    imgs = [np.asarray(ImageOps.fit(Image.fromarray(load_img(files[i])), (640, 480)))
            for i in rnd.choice(len(files), n, replace=False)]
    res = {}
    for sa, sb in [(0, 1), (1, 2), (0, 2)]:
        sat, deltas = 0, []
        for img in imgs:
            outs = []
            for al in np.linspace(0, 1, steps):
                for L, o in zip(q["layers"], orig):
                    if o is not None:
                        L["gamma"][sa] = (1 - al) * o[0][sa] + al * o[0][sb]
                        L["beta"][sa] = (1 - al) * o[1][sa] + al * o[1][sb]
                y, st, d = golden.run(q, img, sa, dump=True)
                sat += sum(int((np.abs(x["M"]) >= golden.M_MAX).sum() + (np.abs(x["B"]) >= golden.B_MAX).sum()) for x in d)
                outs.append(y)
            for L, o in zip(q["layers"], orig):
                if o is not None:
                    L["gamma"][:], L["beta"][:] = o
            deltas.append([float(np.abs(outs[k + 1].astype(int) - outs[k]).mean()) for k in range(steps - 1)])
        res[f"{sa}->{sb}"] = {"saturated_coefficients": sat, "step_mean_abs_change": np.mean(deltas, 0).round(2).tolist()}
        print("integer", sa, "->", sb, res[f"{sa}->{sb}"], flush=True)
    return res


if __name__ == "__main__":
    import sys
    if "--integer" in sys.argv:
        torch.set_num_threads(4)
        r = integer_check()
        with open(os.path.join(ROOT, "runs/style_blend_probe_20261031/integer_report.json"), "w") as f:
            json.dump(r, f, indent=2)
    else:
        main()
