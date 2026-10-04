# raw_bin2 单元测试：随机 RAW10 帧（多帧，含帧首跳过行与帧尾多余行）× Bayer 相位 × vsync 形式 ×
# 黑电平 × 白平衡增益 × gamma 开关；输入每拍 4 像素、可选随机间隔 → iverilog → 与 Python 参考逐像素比对（含帧首标志）
import os
import random
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import gen_gamma  # noqa: E402

IV = os.environ.get("IVERILOG", r"C:\iverilog\bin\iverilog.exe")
VVP = os.environ.get("VVP", os.path.join(os.path.dirname(IV), "vvp.exe"))

TB = r"""`timescale 1ns/1ps
module tb;
    parameter IW = 24, IH = 8, NL = 10, NF = 2, VSMODE = 0, BAY = 0, GR = 256, GG = 256, GB = 256;
    parameter BLK = 64, GAM = 1, SKIP = 0, GAP = 1;
    localparam NW = IW / 4 * NL * NF;
    reg clk = 0, rst = 1;
    always #5 clk = ~clk;
    reg [39:0] mem [0:NW-1];
    initial $readmemh("raw2_in.hex", mem);
    integer ip = 0, seed = 7, f, fr, ln, wd, gap;
    reg v = 0, vs = 0; reg [39:0] d = 0;
    wire ov, osof; wire [23:0] od;
    raw_bin2 #(.IW(IW), .IH(IH)) dut (.clk(clk), .rst(rst), .i_vs(vs), .i_valid(v), .i_data(d),
        .bayer(BAY[1:0]), .blk(BLK[9:0]), .gain_r(GR[11:0]), .gain_g(GG[11:0]), .gain_b(GB[11:0]),
        .gamma_en(GAM[0]), .skip(SKIP[1:0]), .o_valid(ov), .o_sof(osof), .o_data(od));
    always @(posedge clk) if (!rst && ov) $fwrite(f, "%h %0d\n", od, osof);
    initial begin
        f = $fopen("raw2_out.txt", "w");
        repeat (3) @(posedge clk); rst <= 0;
        repeat (5) @(posedge clk);
        for (fr = 0; fr < NF; fr = fr + 1) begin
            // vsync：模式 0 为帧前脉冲；模式 1 为帧期间高电平
            vs <= 1; repeat (3) @(posedge clk);
            if (VSMODE == 0) vs <= 0;
            repeat (4) @(posedge clk);
            for (ln = 0; ln < NL; ln = ln + 1) begin
                for (wd = 0; wd < IW / 4; wd = wd + 1) begin
                    gap = GAP ? ($random(seed) & 3) : 1;
                    if (gap == 0) begin v <= 0; @(posedge clk); end
                    v <= 1; d <= mem[ip]; ip = ip + 1; @(posedge clk);
                end
                if (GAP) begin v <= 0; repeat (6) @(posedge clk); end
            end
            v <= 0;
            if (VSMODE == 1) vs <= 0;
            repeat (40) @(posedge clk);
        end
        repeat (IW + 200) @(posedge clk);
        $fclose(f); $finish;
    end
endmodule
"""

GAMMA = gen_gamma.table()


def ref(img, IW, IH, skip, bay, blk, gains, gam):
    L = img[skip:skip + IH]
    out = []
    for by in range(IH // 2):
        for bx in range(IW // 2):
            s00, s01 = L[2 * by][2 * bx], L[2 * by][2 * bx + 1]
            s10, s11 = L[2 * by + 1][2 * bx], L[2 * by + 1][2 * bx + 1]
            r, g, b = {0: (s00, s01 + s10, s11), 1: (s01, s00 + s11, s10),
                       2: (s10, s00 + s11, s01), 3: (s11, s01 + s10, s00)}[bay]
            v2 = [max(r - blk, 0) * 2, max(g - 2 * blk, 0), max(b - blk, 0) * 2]
            v10 = [min(1023, (v * gn + 256) >> 9) for v, gn in zip(v2, gains)]
            q = [GAMMA[v] if gam else v >> 2 for v in v10]
            out.append((q[0] | q[1] << 8 | q[2] << 16, int(bx == 0 and by == 0)))
    return out


def run(IW, IH, extra, skip, NF, vsmode, bay, blk, gains, gam, gap, seed):
    NL = skip + IH + extra
    rnd = random.Random(seed)
    frames = [[[rnd.randrange(1024) for _ in range(IW)] for _ in range(NL)] for _ in range(NF)]
    frames[0][skip][0] = 1023
    frames[0][skip][1] = 0
    wd = os.path.join(HERE, "work")
    os.makedirs(wd, exist_ok=True)
    with open(os.path.join(wd, "raw2_in.hex"), "w") as f:
        for img in frames:
            for row in img:
                for x in range(0, IW, 4):
                    w = sum(row[x + i] << (10 * i) for i in range(4))
                    f.write(f"{w:010x}\n")
    open(os.path.join(wd, "tb_raw2.v"), "w").write(TB)
    shutil.copy(os.path.join(ROOT, "rtl", "gamma_srgb.mem"), wd)
    exe = os.path.join(wd, "tb_raw2.vvp")
    P = dict(IW=IW, IH=IH, NL=NL, NF=NF, VSMODE=vsmode, BAY=bay, GR=gains[0], GG=gains[1], GB=gains[2],
             BLK=blk, GAM=gam, SKIP=skip, GAP=gap)
    subprocess.run([IV, "-g2012", "-o", exe] + [f"-Ptb.{k}={v}" for k, v in P.items()] +
                   [os.path.join(wd, "tb_raw2.v"), os.path.join(ROOT, "rtl", "raw_bin2.v"),
                    os.path.join(ROOT, "rtl", "common.v"), os.path.join(ROOT, "rtl", "axi_frame.v")],
                   check=True)
    subprocess.run([VVP, "-n", exe], cwd=wd, check=True, capture_output=True)
    got = [(int(a, 16), int(b)) for a, b in (l.split() for l in open(os.path.join(wd, "raw2_out.txt")))]
    exp = sum((ref(img, IW, IH, skip, bay, blk, gains, gam) for img in frames), [])
    ok = got == exp
    msg = ""
    if not ok:
        bad = next((i for i, (g, e) in enumerate(zip(got, exp)) if g != e), min(len(got), len(exp)))
        msg = (f" 首个不一致 @{bad}: got={got[bad] if bad < len(got) else None} "
               f"exp={exp[bad] if bad < len(exp) else None} (len {len(got)}/{len(exp)})")
    print(f"raw_bin2 {IW}x{IH}+{skip}/{extra} vs={'电平' if vsmode else '脉冲'} bayer={bay} blk={blk} "
          f"gain={gains} gamma={gam} gap={gap}: {len(got)}/{len(exp)} {'PASS' if ok else 'FAIL'}{msg}")
    return ok


if __name__ == "__main__":
    # (IW, IH, 帧尾多余行, 帧首跳过行, 帧数, vsync 形式, bayer, 黑电平, 增益 R/G/B, gamma, 随机间隔)
    cases = [(24, 8, 2, 0, 2, 0, 0, 64, (256, 256, 256), 1, 1),
             (24, 8, 0, 2, 2, 1, 1, 64, (440, 273, 420), 1, 1),
             (32, 12, 3, 1, 2, 0, 2, 16, (512, 300, 200), 0, 1),
             (40, 10, 2, 2, 3, 1, 3, 0, (256, 256, 256), 0, 1),
             (1280, 16, 2, 2, 2, 0, 0, 64, (700, 1000, 4095), 1, 0)]     # 整行无间隔：检验 FIFO 深度
    res = [run(*c, seed=i + 1) for i, c in enumerate(cases)]
    sys.exit(0 if all(res) else 1)
