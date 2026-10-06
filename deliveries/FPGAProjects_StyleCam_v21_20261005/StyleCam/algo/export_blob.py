# 导出部署镜像：CPU 经 cfg 寄存器装载的权重 + 各风格归一化系数
#   初始系数：IN 层使用标定集平均统计量；运行时由 FPGA 统计和固件轮换刷新
#   同时评估"固定统计量"相对"逐帧 IN"的画质损失（对教师输出的 PSNR）
# 镜像格式（小端 32 位字）：
#   [0] 0x53544E31 'STN1'  [1] 写次数 N  [2] 风格数  [3] 保留
#   之后 N 组 {CFG_ADDR, CFG_DLO, CFG_DHI}，依次写 0x020/0x024/0x028 寄存器
import argparse
import json
import os
import hashlib
from PIL import Image, ImageOps

import numpy as np
import torch

import gen_rtl
import golden
from eval import load_img
from teacher import load_teacher
from train import DATA, ROOT, image_list


def avg_stats(q, imgs, style):
    # 逐层累加各图的 Σa/n、Σa²/n，求平均，得到"典型场景"的统计量
    acc = None
    for im in imgs:
        _, st, _ = golden.run(q, im, style)
        if acc is None:
            acc = [None if s is None else [np.zeros_like(s[0], float), np.zeros_like(s[1], float)] for s in st]
        for a, s in zip(acc, st):
            if s is not None:
                a[0] += s[0] / s[2]
                a[1] += s[1] / s[2]
    return [None if a is None else (a[0] / len(imgs), a[1] / len(imgs), 1) for a in acc]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="runs/c24_gram")   # 部署模型；改这里会覆盖 sw/net_blob.h、sw/in_params.h
    ap.add_argument("--W", type=int, default=640)
    ap.add_argument("--H", type=int, default=480)
    ap.add_argument("--ncal", type=int, default=16)
    ap.add_argument("--neval", type=int, default=8)
    ap.add_argument("--skip_eval", action="store_true", help="跳过固定统计量画质评估")
    ap.add_argument("--outdir", default="", help="isolated RTL/blob output; defaults to legacy rtl/gen location")
    ap.add_argument("--swdir", default="", help="isolated firmware headers; defaults to legacy sw location")
    ap.add_argument("--cal_vga", action="store_true", help="resize calibration frames to requested W/H")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--contract",default="",help="keep R/S from an integer-forward training contract")
    a = ap.parse_args()
    torch.set_num_threads(a.threads)
    run = os.path.join(ROOT, a.run)
    q = golden.export_float(os.path.join(run, "student.pt"))
    styles = q["styles"]
    ns = len(styles)
    train_files, eval_files = image_list()
    rnd = np.random.RandomState(0)
    cal = [load_img(train_files[i]) for i in rnd.choice(len(train_files), a.ncal, replace=False)]
    if a.cal_vga:
        cal = [np.asarray(ImageOps.fit(Image.fromarray(c), (a.W, a.H), method=Image.Resampling.BILINEAR)) for c in cal]
    if a.contract:
        old=golden.load(a.contract)
        assert old["cfg"]==q["cfg"] and old["styles"]==q["styles"]
        for L,O in zip(q["layers"],old["layers"]):
            assert abs(L["s_y"]-O["s_y"])<1e-10
            L["R"],L["S"]=O["R"],O["S"]
        print("Frozen R/S contract:",a.contract,flush=True)
    else:
        print("标定 R/S:", golden.calibrate(q, cal[:4] if a.cal_vga else [c[:240, :320] for c in cal[:4]], ns), flush=True)

    # 各风格固定统计量 → 系数；硬件系数槽 = 2*风格数（风格 s 占槽 2s、2s+1，供 IN 刷新乒乓）
    stats = [avg_stats(q, cal, s) for s in range(ns)]
    coefs = []
    for i, L in enumerate(q["layers"]):
        Ms, Bs = [], []
        for bank in range(2 * ns):
            M, B = golden.coef_from_stats(L, stats[bank // 2][i], bank // 2)
            Ms.append(M)
            Bs.append(B)
        coefs.append((Ms, Bs))

    # 画质：固定统计量 vs 逐帧 IN（整数模型），均对教师输出
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    T = [] if a.skip_eval else [load_teacher(os.path.join(DATA, "saved_models", f"{s}.pth"), dev) for s in styles]
    res = {}
    for s in (range(0) if a.skip_eval else range(ns)):
        p_dyn, p_fix = [], []
        for f in eval_files[:a.neval]:
            im = load_img(f)
            with torch.no_grad():
                t = T[s](torch.from_numpy(im).permute(2, 0, 1)[None].float().to(dev)).clamp(0, 255)
                t = t.round()[0].permute(1, 2, 0).byte().cpu().numpy()
            y_dyn, _, _ = golden.run(q, im, s)
            y_fix, _, _ = golden.run(q, im, s, prev_stats=stats[s])
            psnr = lambda x: 10 * np.log10(255 ** 2 / np.mean((x.astype(float) - t) ** 2))
            p_dyn.append(psnr(y_dyn))
            p_fix.append(psnr(y_fix))
        res[styles[s]] = dict(dynamic_in=round(float(np.mean(p_dyn)), 2), fixed_stats=round(float(np.mean(p_fix)), 2))
    print(json.dumps(res, ensure_ascii=False, indent=1))

    # 生成 RTL（带初值，便于上电即用）与装载镜像
    outdir = os.path.abspath(a.outdir) if a.outdir else os.path.join(ROOT, "rtl", "gen", f"{os.path.basename(a.run)}_{a.W}x{a.H}")
    geo, nw = gen_rtl.generate(q, a.W, a.H, outdir, coefs, 2 * ns, relative_mem=bool(a.outdir))
    golden.save(q, os.path.join(outdir, "qparams"))      # 标定后的整数参数（固件测试等复用）
    script = [tuple(int(x, 16) if k == 4 else int(x) for k, x in enumerate(l.split()))
              for l in open(os.path.join(outdir, "cfg.txt"))]
    words = [0x53544E31, len(script), ns, 0]
    for layer, sel, lane, addr, data in script:
        words += [(sel << 31) | (lane << 21) | (layer << 16) | addr, data & 0xFFFFFFFF, (data >> 32) & 0x3F]
    blob = np.array(words, dtype="<u4")
    blob.tofile(os.path.join(outdir, "net_blob.bin"))
    sw = os.path.abspath(a.swdir) if a.swdir else os.path.join(ROOT, "sw")
    os.makedirs(sw, exist_ok=True)
    with open(os.path.join(sw, "net_blob.h"), "w") as f:
        f.write("// 自动生成：algo/export_blob.py（%s），勿手改\n#include <stdint.h>\n" % a.run)
        f.write("static const char *const net_styles[] = {%s};\n" % ", ".join(f'"{s}"' for s in styles))
        f.write("#define NET_NSTYLE %d\n#define NET_BLOB_WORDS %d\n" % (ns, len(words)))
        f.write("static const uint32_t net_blob[NET_BLOB_WORDS] = {\n")
        for i in range(0, len(words), 6):
            f.write("    " + ", ".join(f"0x{w:08x}" for w in words[i:i + 6]) + ",\n")
        f.write("};\n")
    # 固件用 IN 层常数表（逐帧刷新 M/Bq 时使用，算法同 golden.coef_from_stats）
    NL = "\n"
    with open(os.path.join(sw, "in_params.h"), "w") as f:
        f.write("// 自动生成：algo/export_blob.py（%s），勿手改" % a.run + NL)
        f.write("// 每个 IN 层：层号、通道数、统计像素数、R、S、s_y、eps、k[c]=s_w*s_x、gamma/beta[风格*cout+c]" + NL)
        f.write("#define IN_S2 %d" % golden.S2 + NL)
        f.write("typedef struct { int layer, cout, npix, R, S; double s_y, eps;"
                " const float *k, *gamma, *beta; } in_layer_t;" + NL)
        in_layers = [i for i, L in enumerate(q["layers"]) if "gamma" in L and "rmean" not in L]
        for i in in_layers:
            L = q["layers"][i]
            for tag, arr in (("k", L["s_w"] * L["s_x"]), ("g", L["gamma"].flatten()), ("b", L["beta"].flatten())):
                f.write("static const float in_%s%d[] = {%s};" % (tag, i, ", ".join("%.9e" % v for v in arr)) + NL)
        f.write("#define IN_NLAYER %d" % len(in_layers) + NL)
        f.write("static const in_layer_t in_layers[IN_NLAYER] = {" + NL)
        for i in in_layers:
            L, g = q["layers"][i], geo[i]
            wo = g["W"] * (2 if L["up"] else 1) // L["stride"]
            ho = g["H"] * (2 if L["up"] else 1) // L["stride"]
            f.write("    {%d, %d, %d, %d, %d, %.9e, %.9e, in_k%d, in_g%d, in_b%d}," %
                    (i, L["cout"], wo * ho, L["R"], L["S"], L["s_y"], L["eps"], i, i, i) + NL)
        f.write("};" + NL)
    json.dump(dict(quality=res, cfg_writes=len(script), blob_bytes=len(words) * 4,
                   checkpoint=os.path.abspath(os.path.join(run, "student.pt")),
                   checkpoint_sha256=hashlib.sha256(open(os.path.join(run, "student.pt"), "rb").read()).hexdigest(),
                   styles=styles, W=a.W, H=a.H, ncal=a.ncal, rs_ncal=0 if a.contract else min(4, a.ncal), cal_vga=a.cal_vga,
                   frozen_contract=a.contract or None,
                   blob_sha256=hashlib.sha256(blob.tobytes()).hexdigest()),
              open(os.path.join(outdir, "export.json"), "w"), ensure_ascii=False, indent=1)
    print(f"RTL/镜像输出：{outdir}；cfg 写次数 {len(script)}，镜像 {len(words) * 4} 字节")


if __name__ == "__main__":
    main()
