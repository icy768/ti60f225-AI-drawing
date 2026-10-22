# 整数金标准模型：定义硬件的逐位运算规格，RTL 仿真结果必须与此逐位一致
#
# 每层运算（全部为整数）：
#   X   : uint8 输入特征图 [Cin,H,W]；up=1 时先最近邻放大 2 倍
#   acc : Σ Wq(int8) * X(uint8)，零填充，stride/groups 同层描述
#   a   = sat19(acc >>> R)                     R 为层常数，a 为 19 位有符号
#   t   = a*M[c] + (Bq[c] << (S-S2)) (+ skip*K) M 18 位有符号，Bq 20 位有符号，K 18 位无符号
#   q   = clip(t >>> S, 0, 255)                 S 为层常数（S>=S2）；舍入偏置已并入 Bq
# IN 统计：硬件对每通道累加 Σa、Σa²（整帧），RISC-V 在帧间隙据此计算下一帧的 M/B
# 输出：末层 12 通道经 PixelShuffle(2) 得到 RGB，out[c,2y+i,2x+j] = q[4c+2i+j,y,x]
import json
import math
import os

import numpy as np
import torch
import torch.nn.functional as F

from tinystyle import QCfg, TinyStyleNet

A_BITS, M_BITS, B_BITS, S2 = 19, 18, 20, 8
A_MAX, M_MAX = (1 << (A_BITS - 1)) - 1, (1 << (M_BITS - 1)) - 1
B_MAX = (1 << (B_BITS - 1)) - 1


def export_float(ck_path):
    # 从 QAT 检查点导出：量化权重、各尺度、归一化参数
    ck = torch.load(ck_path, map_location="cpu", weights_only=False)
    net = TinyStyleNet(**ck["cfg"])
    net.load_state_dict(ck["sd"])
    layers, s_prev = [], 1.0 / 255
    outs_scale = []
    for L in net.layers:
        s = dict(L.spec)
        w = L.conv.weight.detach().double()
        sw = (w.abs().flatten(1).amax(1).clamp(min=1e-8) / 127)
        wq = torch.clamp(torch.round(w / sw.view(-1, 1, 1, 1)), -127, 127)
        s["wq"] = wq.to(torch.int64).numpy()
        s["s_w"] = sw.numpy()
        s["s_x"] = s_prev
        s["s_y"] = float(L.aq.scale())
        if L.norm is not None:
            s["gamma"] = L.norm.gamma.detach().double().numpy()
            s["beta"] = L.norm.beta.detach().double().numpy()
            s["eps"] = L.norm.eps
            if L.norm.mode == "bn":
                s["rmean"] = np.stack([b.running_mean.double().numpy() for b in L.norm.bn])
                s["rvar"] = np.stack([b.running_var.double().numpy() for b in L.norm.bn])
        else:
            s["bias"] = L.conv.bias.detach().double().numpy()
        s["s_skip"] = outs_scale[s["skip"]] if s["skip"] is not None else None
        layers.append(s)
        outs_scale.append(s["s_y"])
        s_prev = s["s_y"]
    return dict(cfg=ck["cfg"], styles=ck["styles"], layers=layers)


def conv_int(x, L):
    # float64 卷积对整数输入是精确的（乘积 < 2^15，和 < 2^30）
    if L["up"]:
        x = F.interpolate(x, scale_factor=2, mode="nearest")
    w = torch.from_numpy(L["wq"]).double()
    return F.conv2d(x, w, None, L["stride"], L["k"] // 2, 1, L["groups"])


def shift_sat(acc, R):
    a = torch.div(acc, 2 ** R, rounding_mode="floor")
    return a.clamp(-A_MAX - 1, A_MAX)


def stats(a):
    # 硬件累加的整数统计量（逐通道 Σa, Σa², 像素数）
    ai = a[0].to(torch.int64).flatten(1)
    return ai.sum(1).numpy(), (ai * ai).sum(1).numpy(), ai.shape[1]


def coef_from_stats(L, st, style):
    # 由统计量计算 M/B（RISC-V 固件将实现同样算法）；BN 模式用滑动统计量
    R, S = L["R"], L["S"]
    k = L["s_w"] * L["s_x"]
    if "gamma" in L:
        g, b = L["gamma"][style], L["beta"][style]
        if "rmean" in L:
            mu_v, var_v = L["rmean"][style], L["rvar"][style]
        else:
            s1, s2, n = st
            mean_a = s1 / n
            var_a = np.maximum(s2 / n - mean_a ** 2, 0.0)
            mu_v = mean_a * (2 ** R) * k
            var_v = var_a * (4 ** R) * k * k
        sig = np.sqrt(var_v + L["eps"])
        mult = g * k / sig
        add = b - g * mu_v / sig
    else:
        mult, add = k, L["bias"]
    M = np.clip(np.round(mult / L["s_y"] * 2.0 ** (S + R)), -M_MAX - 1, M_MAX).astype(np.int64)
    Bq = np.clip(np.round(add / L["s_y"] * 2.0 ** S2) + 2 ** (S2 - 1), -B_MAX - 1, B_MAX).astype(np.int64)
    return M, Bq


def skip_k(L):
    return int(round(L["s_skip"] / L["s_y"] * 2 ** L["S"])) if L["s_skip"] is not None else 0


def requant(a, L, M, B, skip):
    Bs = torch.from_numpy(B * (1 << (L["S"] - S2))).double().view(1, -1, 1, 1)
    t = a * torch.from_numpy(M).double().view(1, -1, 1, 1) + Bs
    if skip is not None:
        t = t + skip * skip_k(L)
    return torch.div(t, 2 ** L["S"], rounding_mode="floor").clamp(0, 255)


def run(q, img, style, prev_stats=None, dump=False):
    # img: uint8 [H,W,3]；prev_stats=None 表示用本帧统计（等价于静止画面第二帧）
    # 返回 输出 RGB、本帧统计量、（可选）逐层中间结果
    x = torch.from_numpy(np.ascontiguousarray(img)).permute(2, 0, 1)[None].double()
    feats, st_all, dumps = [], [], []
    for i, L in enumerate(q["layers"]):
        acc = conv_int(x, L)
        a = shift_sat(acc, L["R"])
        st = stats(a) if ("gamma" in L and "rmean" not in L) else None
        st_all.append(st)
        use = st if prev_stats is None else prev_stats[i]
        M, B = coef_from_stats(L, use, style)
        skip = feats[L["skip"]] if L["skip"] is not None else None
        x = requant(a, L, M, B, skip)
        feats.append(x)
        if dump:
            dumps.append(dict(a=a[0].to(torch.int64).numpy(), q=x[0].to(torch.uint8).numpy(), M=M, B=B))
    y = F.pixel_shuffle(x, 2)[0].permute(1, 2, 0).to(torch.uint8).numpy()
    return y, st_all, dumps


def calibrate(q, imgs, n_styles, margin=2.0):
    # 标定各层 R（acc 右移位数）与 S（输出移位）：
    #   R 使 max|acc|*margin 落入 19 位；S 使 max|M|*margin 落入 18 位且 K 不溢出
    # 逐层标定：本层 R/S 由全部（图像 x 风格）样本确定后，再推进到下一层
    streams = [(torch.from_numpy(np.ascontiguousarray(im)).permute(2, 0, 1)[None].to(torch.uint8), s)
               for im in imgs for s in range(n_styles)]
    feats = [[] for _ in streams]
    xs = [x for x, _ in streams]
    for i, L in enumerate(q["layers"]):
        is_in = "gamma" in L and "rmean" not in L
        accs = [conv_int(x.double(), L) for x in xs]
        maxacc = max(float(a.abs().max()) for a in accs)
        L["R"] = max(0, math.ceil(math.log2(maxacc * margin + 1)) - (A_BITS - 1))
        As = [shift_sat(a, L["R"]) for a in accs]
        sts = [stats(a) if is_in else None for a in As]
        maxmult = max(float(np.abs(coef_from_stats_raw(L, st, s)[0]).max())
                      for st, (_, s) in zip(sts, streams))
        S = math.floor(math.log2(M_MAX / (maxmult * margin)))
        if L["s_skip"] is not None:
            S = min(S, math.floor(math.log2(M_MAX / (L["s_skip"] / L["s_y"]))))
        assert S >= S2, f"{L['name']}: S={S} < S2"
        L["S"] = S
        for j, (a, st, (_, s)) in enumerate(zip(As, sts, streams)):
            M, B = coef_from_stats(L, st, s)
            skip = feats[j][L["skip"]].double() if L["skip"] is not None else None
            xs[j] = requant(a, L, M, B, skip).to(torch.uint8)
            feats[j].append(xs[j])
    return [(L["name"], L["R"], L["S"]) for L in q["layers"]]


def coef_from_stats_raw(L, st, style):
    # 未取整、未限幅的 M（S=0 时的真实乘数 * 2^R），用于标定 S
    R = L["R"]
    k = L["s_w"] * L["s_x"]
    if "gamma" in L:
        g = L["gamma"][style]
        if "rmean" in L:
            var_v = L["rvar"][style]
        else:
            s1, s2, n = st
            var_a = np.maximum(s2 / n - (s1 / n) ** 2, 0.0)
            var_v = var_a * (4 ** R) * k * k
        mult = g * k / np.sqrt(var_v + L["eps"])
    else:
        mult = k
    return mult / L["s_y"] * 2.0 ** R, None


def save(q, path):
    # 保存整数参数（npz）与层常数（json），供 RTL 生成器使用
    arrs, meta = {}, []
    for i, L in enumerate(q["layers"]):
        m = {k: v for k, v in L.items() if not isinstance(v, np.ndarray)}
        m["K"] = skip_k(L)
        meta.append(m)
        for k, v in L.items():
            if isinstance(v, np.ndarray):
                arrs[f"{i}_{k}"] = v
    np.savez(path + ".npz", **arrs)
    json.dump(dict(cfg=q["cfg"], styles=q["styles"], layers=meta), open(path + ".json", "w"),
              ensure_ascii=False, indent=1)


def load(path):
    meta = json.load(open(path + ".json"))
    arrs = np.load(path + ".npz")
    layers = []
    for i, m in enumerate(meta["layers"]):
        L = dict(m)
        for k in arrs.files:
            if k.startswith(f"{i}_"):
                L[k[len(f"{i}_"):]] = arrs[k]
        layers.append(L)
    return dict(cfg=meta["cfg"], styles=meta["styles"], layers=layers)
