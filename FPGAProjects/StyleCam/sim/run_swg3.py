# swg3 单元测试：随机输入 → iverilog 仿真 → 与 Python 参考逐字比对
import os
import random
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RTL = os.path.join(HERE, "..", "rtl")
IVERILOG = os.environ.get("IVERILOG", r"C:\iverilog\bin\iverilog.exe")
VVP = os.environ.get("VVP", os.path.join(os.path.dirname(IVERILOG), "vvp.exe"))


def ref(frames, G, NG, W, H, S, UP):
    out = []
    WO, HO = (2 * W, 2 * H) if UP else ((W + S - 1) // S, (H + S - 1) // S)
    for img in frames:  # img[y][x][g] = word(int)
        for oy in range(HO):
            for ox in range(WO):
                for g in range(NG):
                    for t in range(9):
                        ky, kx = divmod(t, 3)
                        if UP:
                            uy, ux = oy + ky - 1, ox + kx - 1
                            pad = not (0 <= uy < 2 * H and 0 <= ux < 2 * W)
                            iy, ix = uy >> 1, ux >> 1
                        else:
                            iy, ix = oy * S + ky - 1, ox * S + kx - 1
                            pad = not (0 <= iy < H and 0 <= ix < W)
                        out.append((0 if pad else img[iy][ix][g], t, g))
    return out


def run(G, NG, W, H, S, UP, nframes=2, seed=1, b2=0):
    rnd = random.Random(seed)
    frames = [[[[rnd.getrandbits(G * 8) for _ in range(NG)] for _ in range(W)] for _ in range(H)]
              for _ in range(nframes)]
    wd = os.path.join(HERE, "work")
    os.makedirs(wd, exist_ok=True)
    with open(os.path.join(wd, "swg_in.hex"), "w") as f:
        for img in frames:
            for row in img:
                for px in row:
                    for w in px:
                        f.write(f"{w:0{G*2}x}\n")
    exe = os.path.join(wd, "tb_swg3.vvp")
    params = dict(G=G, NG=NG, W=W, H=H, STRIDE=S, UP=UP, NFRAMES=nframes, SEED=seed, NR=2 if UP else 3, B2=b2)
    cmd = [IVERILOG, "-g2012", "-o", exe] + [f"-Ptb_swg3.{k}={v}" for k, v in params.items()] + \
          [os.path.join(HERE, "tb_swg3.v"), os.path.join(RTL, "swg3.v"), os.path.join(RTL, "swg3b.v"), os.path.join(RTL, "common.v")]
    subprocess.run(cmd, check=True)
    r = subprocess.run([VVP, "-n", exe], cwd=wd, capture_output=True, text=True)
    msg = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr
    got = []
    for line in open(os.path.join(wd, "swg_out.txt")):
        d, t, g = line.split()
        got.append((int(d, 16), int(t), int(g)))
    exp = ref(frames, G, NG, W, H, S, UP)
    ok = got == exp
    if not ok:
        n = min(len(got), len(exp))
        bad = next((i for i in range(n) if got[i] != exp[i]), n)
        print(f"  首个不一致 @{bad}: got={got[bad] if bad < len(got) else None} exp={exp[bad] if bad < len(exp) else None}"
              f" (len got {len(got)} exp {len(exp)})")
    print(f"{'swg3b' if b2 else 'swg3 '} G={G} NG={NG} W={W} H={H} S={S} UP={UP}: {'PASS' if ok else 'FAIL'}  {msg}")
    return ok


if __name__ == "__main__":
    cases = [(4, 2, 7, 5, 1, 0), (4, 2, 8, 6, 2, 0), (4, 2, 7, 5, 2, 0), (4, 2, 5, 4, 1, 1),
             (3, 1, 16, 12, 2, 0), (4, 6, 10, 6, 1, 0), (4, 3, 6, 5, 1, 1), (4, 1, 4, 4, 1, 0),
             (4, 4, 320, 5, 2, 0)]      # 行缓冲 3x320x4=3840 深：覆盖 sdpram 分段
    res = [run(*c, seed=i + 1) for i, c in enumerate(cases)]
    # swg3b（stride=1，2 行 + 待提交缓冲）
    cases_b = [(4, 2, 7, 5), (4, 6, 10, 6), (4, 1, 4, 4), (4, 3, 12, 9), (4, 4, 5, 3), (3, 1, 16, 8),
               (4, 4, 320, 4)]          # 2x320x4=2560 深：覆盖 sdpram 分段
    res += [run(g, ng, w, h, 1, 0, seed=20 + i, b2=1) for i, (g, ng, w, h) in enumerate(cases_b)]
    sys.exit(0 if all(res) else 1)
