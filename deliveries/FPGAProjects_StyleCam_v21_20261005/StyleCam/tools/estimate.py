# 资源估算（综合前）：M10K 块数与乘法器个数，按生成的层参数逐个存储器计算
# M10K 按 10240 位、可配置 8192x1/4096x2/2048x5/1024x10/512x20/256x40（取最省配置，宽度拼接、深度级联）
import argparse
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "algo"))

MODES = [(8192, 1), (4096, 2), (2048, 5), (1024, 10), (512, 20), (256, 40)]


def m10k(width, depth):
    return min(math.ceil(width / w) * math.ceil(depth / d) for d, w in MODES)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--q", default="rtl/gen/c24_gram_640x480/qparams")
    ap.add_argument("--W", type=int, default=640)
    ap.add_argument("--H", type=int, default=480)
    ap.add_argument("--nsty", type=int, default=8)
    ap.add_argument("--pe_d2", type=int, default=6)
    ap.add_argument("--dw", type=int, default=128, help="DDR AXI 数据位宽")
    ap.add_argument("--lb3", action="store_true", help="全部用 3 行行缓冲（旧方案）")
    ap.add_argument("--cam", default="raw2", choices=["raw2", "raw3", "rgb"],
                    help="摄像头前端：raw2=raw_bin2（IMX219 1280x960），raw3=raw_bin3（SC431HAI 1920x1440），rgb=cam_scale3")
    a = ap.parse_args()
    import golden
    import gen_rtl
    gen_rtl.PE_TABLE["d2"] = a.pe_d2
    q = golden.load(os.path.join(ROOT, a.q))
    geo = gen_rtl.layer_geom(q, a.W, a.H)
    rows, mults = [], []
    for i, (L, g) in enumerate(zip(q["layers"], geo)):
        GI, NG = g["GI"], L["cin"] // g["GI"]
        if L["k"] == 3:
            nr = 3 if (L["stride"] == 2 and not a.lb3) else (3 if a.lb3 else 2)
            rows.append((f"{L['name']} 行缓冲", GI * 8, nr * g["W"] * NG))
        if g["DW"]:
            rows.append((f"{L['name']} 权重", GI * 8, NG * 9))
            mults.append((f"{L['name']} dw", GI, "8x8"))
        else:
            NI = NG * (9 if L["k"] == 3 else 1)
            NF = L["cout"] // g["PE"]
            rows.append((f"{L['name']} 权重", g["PE"] * GI * 8, NI * NF))
            mults.append((f"{L['name']} PE{g['PE']}xG{GI}", g["PE"] * GI, "8x8"))
        rows.append((f"{L['name']} 系数", 38, a.nsty * L["cout"]))
        mults.append((f"{L['name']} requant", 1, "19x18"))
        if L["skip"] is not None:
            mults.append((f"{L['name']} 残差K", 1, "9x18"))
    cam_rows = {"raw2": [("raw_bin2 偶数行缓存", 40, 2 * a.W // 4), ("raw_bin2 像素对 FIFO", 63, 256),
                         ("raw_bin2 gamma R", 8, 1024), ("raw_bin2 gamma G", 8, 1024), ("raw_bin2 gamma B", 8, 1024)],
                "raw3": [("raw_bin3 块列累加 0", 48, a.W // 2 + 1), ("raw_bin3 块列累加 1", 48, a.W // 2 + 1),
                         ("raw_bin3 块列 FIFO 0", 25, 256), ("raw_bin3 块列 FIFO 1", 25, 256)],
                "rgb": [("cam_scale3 行缓存", 36, a.W)]}
    cam_mults = {"raw2": [("raw_bin2 白平衡", 3, "11x12")],
                 "raw3": [("raw_bin3 白平衡", 6, "20x12"), ("raw_bin3 x0.8", 2, "13x16")],
                 "rgb": [("cam_scale3 /9", 3, "12x14")]}
    rows += [("pixshuf 奇数行", 48, a.W // 2)] + cam_rows[a.cam] + [
             ("motion 块列累加", 16, a.W // 16),
             ("motion 上帧块值", 8, (a.W // 16) * (a.H // 16)),
             ("摄像头跨域 FIFO", 25, 1024),
             ("视频跨域 FIFO", 24, 2048),
             ("OSD 文字", 8, 2048),
             ("OSD 字库", 8, 1536),
             ("AXI 写 FIFO x2", a.dw, 32), ("AXI 写 FIFO x2 ", a.dw, 32),
             ("AXI 读 FIFO x2", a.dw, 64), ("AXI 读 FIFO x2 ", a.dw, 64)]
    mults += [("in_stats 平方", 1, "19x19")] + cam_mults[a.cam]
    tot = 0
    nn = 0
    print(f"{'存储器':<22}{'位宽':>6}{'深度':>8}{'M10K':>6}")
    for name, w, d in rows:
        n = m10k(w, d)
        tot += n
        if any(k in name for k in ("行缓冲", "权重", "系数", "pixshuf")):
            nn += n
        print(f"{name:<22}{w:>6}{d:>8}{n:>6}")
    nm = sum(c for _, c, _ in mults)
    print(f"\nNN 部分 M10K {nn}，视觉子系统合计 M10K {tot}（Ti60 共 256）")
    print(f"乘法器 {nm} 个（8x8 {sum(c for _, c, t in mults if t == '8x8')} 个，宽乘法 "
          f"{sum(c for _, c, t in mults if t != '8x8')} 个；Ti60 DSP 共 160）")
    json.dump(dict(m10k_total=tot, m10k_nn=nn, mults=nm), open(os.path.join(ROOT, "docs", "estimate.json"), "w"))


if __name__ == "__main__":
    main()
