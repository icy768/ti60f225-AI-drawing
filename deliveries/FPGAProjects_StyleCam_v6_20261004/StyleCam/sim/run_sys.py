# 整链路仿真：生成 NN、摄像头帧 → iverilog → 比对显示输出的原图区、风格图区（模式 0）与 1.5 倍全屏（模式 1）
import argparse
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "algo"))
import gen_rtl  # noqa: E402
import golden   # noqa: E402

# Allow a checked-in project to run on machines where Icarus is installed in
# a tool cache rather than C:\iverilog.  The default remains compatible with
# the original lab setup.
IV = os.environ.get("IVERILOG", r"C:\iverilog\bin\iverilog.exe")
VVP = os.environ.get("VVP", os.path.join(os.path.dirname(IV), "vvp.exe"))
IW, IH, XOFF, CW = 112, 72, 8, 96
NW, NH = CW // 3, IH // 3
H_ACT, V_ACT, VY0 = 80, 40, 8
RTL_FILES = ["vision_top.v", "vision_core.v", "disp.v", "cam_scale3.v", "raw_bin3.v", "raw_bin2.v", "motion_det.v", "axi_frame.v", "axi_arb.v",
             "conv_layer.v", "swg3.v", "swg3b.v", "mac.v", "requant.v", "common.v"]


def downscale(img):
    out = np.zeros((NH, NW, 3), np.uint8)
    for oy in range(NH):
        for ox in range(NW):
            s = img[oy * 3:oy * 3 + 3, XOFF + ox * 3:XOFF + ox * 3 + 3].astype(np.int64).sum((0, 1))
            out[oy, ox] = ((s * 7282 + 32768) >> 16) & 0xFF
    return out


def read_frame(path):
    px = [int(l, 16) for l in open(path) if l.strip()]
    a = np.array(px, np.int64).reshape(V_ACT, H_ACT)
    return np.stack([a & 0xFF, (a >> 8) & 0xFF, (a >> 16) & 0xFF], -1).astype(np.uint8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--contract', required=True)
    ap.add_argument('--image', required=True)
    args = ap.parse_args()
    from PIL import Image
    q = golden.load(args.contract)
    cam = np.asarray(Image.open(args.image).convert('RGB').resize((IW, IH))).copy()
    A = downscale(cam)
    B, st_gold, dumps = golden.run(q, A, 0, dump=True)
    banks = 2 * len(q['styles'])
    coefs = [([d["M"]] * banks, [d["B"]] * banks) for d in dumps]
    wd = os.path.join(HERE, "work", "sys")
    gen_rtl.generate(q, NW, NH, wd, coefs, banks, relative_mem=True)
    with open(os.path.join(wd, "cam.hex"), "w") as f:
        for y in range(IH):
            for x in range(0, IW, 2):
                p0 = int(cam[y, x, 0]) | int(cam[y, x, 1]) << 8 | int(cam[y, x, 2]) << 16
                p1 = int(cam[y, x + 1, 0]) | int(cam[y, x + 1, 1]) << 8 | int(cam[y, x + 1, 2]) << 16
                f.write(f"{(p1 << 24) | p0:012x}\n")
    import shutil
    shutil.copy(os.path.join(ROOT, "rtl", "font8x16.mem"), wd)
    srcs = [os.path.join(HERE, "tb_sys.v"), os.path.join(HERE, "axi_mem.v"), os.path.join(wd, "stylenet_top.v")] + \
           [os.path.join(ROOT, "rtl", f) for f in RTL_FILES]
    exe = os.path.join(wd, "tb_sys.vvp")
    nn_async = int(os.environ.get("NN_ASYNC", "1"))
    subprocess.run([IV, "-g2012", "-I", HERE, f"-Ptb_sys.NN_ASYNC={nn_async}", "-o", exe] + srcs, check=True, capture_output=True)
    print(f"NN_ASYNC={nn_async}")
    r = subprocess.run([VVP, "-n", exe], cwd=wd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=240, check=True)
    if 'error:' in r.stderr.lower() or 'TIMEOUT' in r.stdout:
        raise RuntimeError(r.stdout + r.stderr)
    sim_text = "\n".join(l for l in r.stdout.splitlines() if "$finish" not in l)
    # Windows consoles may use GBK; simulation diagnostics are UTF-8-safe even
    # when a vendor message contains a replacement character.
    sys.stdout.buffer.write((sim_text + "\n").encode("utf-8", errors="replace"))

    ok = True
    # 统计寄存器读出 vs golden（第 1 层）
    hw = []
    for l in open(os.path.join(wd, "stats_sys.txt")):
        a, b, c, d = (int(v) for v in l.split())
        s1 = (a | (b << 32)) & ((1 << 40) - 1)
        s1 = s1 - (1 << 40) if s1 >> 39 else s1
        hw.append((s1, c | (d << 32)))
    g1, g2, _ = st_gold[1]
    e_st = sum(1 for (x, y), gx, gy in zip(hw, g1, g2) if x != int(gx) or y != int(gy))
    print(f"APB 读出 IN 统计（层 1，24 通道）：不一致 {e_st}")
    ok &= e_st == 0
    # 摄像头帧统计寄存器（AE/AWB）vs 降采样原图（静止画面，任一帧均相同）
    cs = next(l.split()[1:] for l in r.stdout.splitlines() if l.startswith("CAMSTAT"))
    sr, sg, sb, nh, sq = (int(v) for v in cs)
    a64 = A.astype(np.int64)
    exp_st = (int(a64[..., 0].sum()), int(a64[..., 1].sum()), int(a64[..., 2].sum()), int((A >= 250).any(-1).sum()))
    e_cs = (sr, sg, sb, nh) != exp_st or sq == 0
    print(f"摄像头帧统计：读出 {(sr, sg, sb, nh)} 期望 {exp_st} 帧序号 {sq} {'不一致' if e_cs else '一致'}")
    ok &= not e_cs
    f0 = read_frame(os.path.join(wd, "disp_m0.txt"))
    left, right = f0[VY0:VY0 + NH, 0:NW], f0[VY0:VY0 + NH, NW:2 * NW]
    e1, e2 = int((left != A).any(-1).sum()), int((right != B).any(-1).sum())
    print(f"模式 0：原图区不一致像素 {e1}/{NW*NH}，风格图区不一致像素 {e2}/{NW*NH}")
    ok &= e1 == 0 and e2 == 0
    osd = f0[0:16, 64:80]
    print(f"OSD 区：白色字形像素 {int((osd == 255).all(-1).sum())}，黄色字形像素 "
          f"{int(((osd[..., 0] == 255) & (osd[..., 1] == 0xE0) & (osd[..., 2] == 0)).sum())}")
    f1 = read_frame(os.path.join(wd, "disp_m1.txt"))
    FW, FH = NW * 3 // 2, NH * 3 // 2
    FX0, FY0 = (H_ACT - FW) // 2, (V_ACT - FH) // 2
    exp1 = np.zeros((FH, FW, 3), np.uint8)
    for y in range(FH):
        for x in range(FW):
            exp1[y, x] = B[2 * y // 3, 2 * x // 3]
    e3 = int((f1[FY0:FY0 + FH, FX0:FX0 + FW] != exp1).any(-1).sum())
    print(f"模式 1：1.5 倍全屏区不一致像素 {e3}/{FW*FH}")
    ok &= e3 == 0
    from PIL import Image
    Image.fromarray(np.concatenate([f0, f1], 1)).resize((H_ACT * 2 * 6, V_ACT * 6), Image.NEAREST) \
        .save(os.path.join(ROOT, "docs", "sim_display.png"))
    print("整链路", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
