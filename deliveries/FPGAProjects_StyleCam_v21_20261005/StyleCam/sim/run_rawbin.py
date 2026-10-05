# raw_bin3 单元测试：随机 RAW10 帧（多帧）× Bayer 相位 × vsync 形式（脉冲/电平）× 白平衡增益
# 输入每拍 4 像素、随机间隔 → iverilog → 与 Python 参考逐像素比对（含帧首标志）
import os
import random
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
IV = os.environ.get("IVERILOG", r"C:\iverilog\bin\iverilog.exe")
VVP = os.environ.get("VVP", os.path.join(os.path.dirname(IV), "vvp.exe"))

TB = r"""`timescale 1ns/1ps
module tb;
    parameter IW = 24, IH = 9, NF = 2, VSMODE = 0, BAY = 0, GR = 256, GG = 256, GB = 256;
    localparam NW = IW / 4 * IH * NF;
    reg clk = 0, rst = 1;
    always #5 clk = ~clk;
    reg [39:0] mem [0:NW-1];
    initial $readmemh("raw_in.hex", mem);
    integer ip = 0, seed = 11, f, k, fr, ln, wd, gap;
    reg v = 0, vs = 0; reg [39:0] d = 0;
    wire ov, osof; wire [23:0] od;
    raw_bin3 #(.IW(IW), .IH(IH)) dut (.clk(clk), .rst(rst), .i_vs(vs), .i_valid(v), .i_data(d),
        .bayer(BAY[1:0]), .gain_r(GR[11:0]), .gain_g(GG[11:0]), .gain_b(GB[11:0]),
        .o_valid(ov), .o_sof(osof), .o_data(od), .o_ready(1'b1));
    always @(posedge clk) if (!rst && ov) $fwrite(f, "%h %0d\n", od, osof);
    initial begin
        f = $fopen("raw_out.txt", "w");
        repeat (3) @(posedge clk); rst <= 0;
        repeat (5) @(posedge clk);
        for (fr = 0; fr < NF; fr = fr + 1) begin
            // vsync：模式 0 为帧前脉冲；模式 1 为帧期间高电平
            vs <= 1; repeat (3) @(posedge clk);
            if (VSMODE == 0) vs <= 0;
            repeat (4) @(posedge clk);
            for (ln = 0; ln < IH; ln = ln + 1) begin
                for (wd = 0; wd < IW / 4; wd = wd + 1) begin
                    gap = $random(seed) & 3;
                    if (gap == 0) begin v <= 0; @(posedge clk); end
                    v <= 1; d <= mem[ip]; ip = ip + 1; @(posedge clk);
                end
                v <= 0; repeat (6) @(posedge clk);
            end
            if (VSMODE == 1) vs <= 0;
            repeat (40) @(posedge clk);
        end
        repeat (200) @(posedge clk);
        $fclose(f); $finish;
    end
endmodule
"""


def ref(img, IW, IH, bay, gains):
    out = []
    pos = {0: ((0, 0), (1, 1), [(0, 1), (1, 0)]), 1: ((0, 1), (1, 0), [(0, 0), (1, 1)]),
           2: ((1, 0), (0, 1), [(0, 0), (1, 1)]), 3: ((1, 1), (0, 0), [(0, 1), (1, 0)])}[bay]
    for by in range(IH // 3):
        for bx in range(IW // 3):
            S = [[0, 0], [0, 0]]
            N = [[0, 0], [0, 0]]
            for r in range(3 * by, 3 * by + 3):
                for c in range(3 * bx, 3 * bx + 3):
                    S[r % 2][c % 2] += img[r][c]
                    N[r % 2][c % 2] += 1
            (ri, rj), (bi, bj), gp = pos
            vr = S[ri][rj] * 4 // N[ri][rj]
            vb = S[bi][bj] * 4 // N[bi][bj]
            sg = sum(S[i][j] for i, j in gp)
            ng = sum(N[i][j] for i, j in gp)
            vg = sg if ng == 4 else (sg * 52429) >> 16
            q = [min(255, (v * g + 2048) >> 12) for v, g in zip((vr, vg, vb), gains)]
            out.append((q[0] | q[1] << 8 | q[2] << 16, int(bx == 0 and by == 0)))
    return out


def run(IW, IH, NF, vsmode, bay, gains, seed):
    rnd = random.Random(seed)
    frames = [[[rnd.randrange(1024) for _ in range(IW)] for _ in range(IH)] for _ in range(NF)]
    frames[0][0][0] = 1023
    wd = os.path.join(HERE, "work")
    os.makedirs(wd, exist_ok=True)
    with open(os.path.join(wd, "raw_in.hex"), "w") as f:
        for img in frames:
            for row in img:
                for x in range(0, IW, 4):
                    w = sum(row[x + i] << (10 * i) for i in range(4))
                    f.write(f"{w:010x}\n")
    open(os.path.join(wd, "tb_raw.v"), "w").write(TB)
    exe = os.path.join(wd, "tb_raw.vvp")
    P = dict(IW=IW, IH=IH, NF=NF, VSMODE=vsmode, BAY=bay, GR=gains[0], GG=gains[1], GB=gains[2])
    subprocess.run([IV, "-g2012", "-o", exe] + [f"-Ptb.{k}={v}" for k, v in P.items()] +
                   [os.path.join(wd, "tb_raw.v"), os.path.join(HERE, "..", "rtl", "raw_bin3.v"),
                    os.path.join(HERE, "..", "rtl", "common.v"), os.path.join(HERE, "..", "rtl", "axi_frame.v")],
                   check=True)
    subprocess.run([VVP, "-n", exe], cwd=wd, check=True, capture_output=True)
    got = [(int(a, 16), int(b)) for a, b in (l.split() for l in open(os.path.join(wd, "raw_out.txt")))]
    exp = sum((ref(img, IW, IH, bay, gains) for img in frames), [])
    ok = got == exp
    msg = ""
    if not ok:
        bad = next((i for i, (g, e) in enumerate(zip(got, exp)) if g != e), min(len(got), len(exp)))
        msg = f" 首个不一致 @{bad}: got={got[bad] if bad < len(got) else None} exp={exp[bad] if bad < len(exp) else None} (len {len(got)}/{len(exp)})"
    print(f"raw_bin3 {IW}x{IH} vs={'电平' if vsmode else '脉冲'} bayer={bay} gain={gains}: "
          f"{len(got)}/{len(exp)} {'PASS' if ok else 'FAIL'}{msg}")
    return ok


if __name__ == "__main__":
    cases = [(24, 9, 2, 0, 0, (256, 256, 256)), (24, 9, 2, 1, 1, (280, 255, 350)),
             (36, 12, 2, 0, 2, (512, 300, 200)), (48, 18, 2, 1, 3, (256, 256, 256))]
    res = [run(*c, seed=i + 1) for i, c in enumerate(cases)]
    sys.exit(0 if all(res) else 1)
