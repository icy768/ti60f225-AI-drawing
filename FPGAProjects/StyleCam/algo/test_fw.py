# 固件 IN 刷新逻辑的 PC 端验证：gcc 编译 sw/vision.c + 测试壳，喂入金标准统计量，
# 检查写出的 M/Bq 与 golden.coef_from_stats 一致（允许浮点常数取整带来的 ±1），以及乒乓槽顺序
import argparse
import os
import subprocess

import numpy as np

import golden
from eval import load_img
from train import ROOT, image_list

GCC = r"D:\mingw64\mingw64\bin\gcc.exe"


def sx(v, bits):
    return v - (1 << bits) if v >> (bits - 1) else v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gen", default="rtl/gen/c24_gram_640x480")   # 须与 sw/in_params.h 的来源模型一致
    ap.add_argument("--style", type=int, default=1)
    a = ap.parse_args()
    gen = os.path.join(ROOT, a.gen)
    q = golden.load(os.path.join(gen, "qparams"))
    for L in q["layers"]:
        L["skip"] = L.get("skip")
    _, ev = image_list()
    from PIL import Image
    img = np.asarray(Image.fromarray(load_img(ev[3])).resize((640, 480), Image.BILINEAR))
    _, st, _ = golden.run(q, img, a.style)
    wd = os.path.join(ROOT, "sw", "test", "work")
    os.makedirs(wd, exist_ok=True)
    with open(os.path.join(wd, "stats.txt"), "w") as f:
        for i, s in enumerate(st):
            if s is not None:
                for c in range(len(s[0])):
                    f.write(f"{i} {c} {int(s[0][c])} {int(s[1][c])}\n")
    exe = os.path.join(wd, "host_test.exe")
    sw = os.path.join(ROOT, "sw")
    env = dict(os.environ, PATH=os.path.dirname(GCC) + os.pathsep + os.environ["PATH"])
    subprocess.run([GCC, "-O2", "-Wall", "-D__USE_MINGW_ANSI_STDIO=1", "-DVISION_HOST_TEST", "-I", sw,
                    os.path.join(sw, "test", "host_test.c"), os.path.join(sw, "vision.c"), "-lm", "-o", exe],
                   check=True, env=env)
    out = os.path.join(wd, "out.txt")
    subprocess.run([exe, os.path.join(wd, "stats.txt"), out, str(a.style)], check=True, env=env)

    # 解析写记录
    events = [l.split() for l in open(out)]
    exp = {}
    for i, L in enumerate(q["layers"]):
        if st[i] is not None:
            exp[i] = golden.coef_from_stats(L, st[i], a.style)
    maxdm = maxdb = 0
    rounds, cur, bad = [], [], 0
    for e in events:
        if e[0] == "cfg":
            addr, lo, hi = int(e[1]), int(e[2]), int(e[3])
            layer, idx = (addr >> 16) & 31, addr & 0xFFF
            cout = q["layers"][layer]["cout"]
            bank, c = divmod(idx, cout)
            M = sx(((hi & 0x3F) << 12) | (lo >> 20), 18)
            B = sx(lo & 0xFFFFF, 20)
            eM, eB = int(exp[layer][0][c]), int(exp[layer][1][c])
            maxdm, maxdb = max(maxdm, abs(M - eM)), max(maxdb, abs(B - eB))
            cur.append((layer, bank))
        elif e[0] == "style":
            rounds.append((int(e[1]), sorted(set(cur))))
            cur = []
    print(f"写记录 {sum(1 for e in events if e[0] == 'cfg')} 条，M 最大偏差 {maxdm}，Bq 最大偏差 {maxdb}")
    print("每轮（切换到的槽，写入的 (层,槽)）：")
    for r in rounds[:6]:
        print("  ", r)
    # 槽应在 2s/2s+1 间交替，且每轮写入的槽 = 切换到的槽
    ok_bank = all(all(b == r[0] for _, b in r[1]) for r in rounds[1:]) and \
        all(r[0] in (2 * a.style, 2 * a.style + 1) for r in rounds)
    alt = all(rounds[i][0] != rounds[i + 1][0] for i in range(1, len(rounds) - 1))
    ok = maxdm <= 1 and maxdb <= 1 and ok_bank and alt
    print("固件 IN 刷新：", "PASS" if ok else "FAIL")


if __name__ == "__main__":
    main()
