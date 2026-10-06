# motion_det 单元测试：多帧随机图（局部变化）→ 与 Python 参考比对每帧运动块数、Σbx、Σby
import os
import random
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
IV = os.environ.get("IVERILOG", r"C:\iverilog\bin\iverilog.exe")
VVP = os.environ.get("VVP", os.path.join(os.path.dirname(IV), "vvp.exe"))
W, H, BS, NF, TH = 64, 32, 8, 4, 10

TB = r"""`timescale 1ns/1ps
module tb;
    parameter W = %d, H = %d, BS = %d, NF = %d, TH = %d;
    localparam N = W * H * NF;
    reg clk = 0, rst = 1;
    always #5 clk = ~clk;
    reg [23:0] mem [0:N-1];
    initial $readmemh("mot_in.hex", mem);
    integer ip = 0, seed = 3, f;
    reg v = 0, sof = 0; reg [23:0] d = 0;
    wire [15:0] cnt; wire [23:0] sx, sy; wire done;
    motion_det #(.W(W), .H(H), .BS(BS)) dut (.clk(clk), .rst(rst), .i_valid(v), .i_sof(sof), .i_data(d),
        .th(TH[7:0]), .m_cnt(cnt), .m_sx(sx), .m_sy(sy), .frame_done(done));
    initial begin f = $fopen("mot_out.txt", "w"); repeat (3) @(posedge clk); rst <= 0; end
    always @(posedge clk) if (!rst && done) $fwrite(f, "%%0d %%0d %%0d\n", cnt, sx, sy);
    always @(posedge clk) if (!rst) begin
        if (ip < N && ($random(seed) & 1)) begin
            v <= 1; d <= mem[ip]; sof <= (ip %% (W * H)) == 0; ip <= ip + 1;
        end else begin v <= 0; sof <= 0; end
        if (ip == N) begin v <= 0; repeat (20) @(posedge clk); $fclose(f); $finish; end
    end
endmodule
""" % (W, H, BS, NF, TH)


def blocks(img):
    bw, bh = W // BS, H // BS
    out = [[0] * bw for _ in range(bh)]
    for by in range(bh):
        for bx in range(bw):
            s = 0
            for y in range(by * BS, by * BS + BS):
                for x in range(bx * BS, bx * BS + BS):
                    r, g, b = img[y][x]
                    s += (r + 2 * g + b) >> 2
            out[by][bx] = s >> ((BS * BS).bit_length() - 1)
    return out


def main():
    rnd = random.Random(2)
    base = [[[rnd.randrange(256) for _ in range(3)] for _ in range(W)] for _ in range(H)]
    frames = []
    for k in range(NF):
        img = [[list(p) for p in row] for row in base]
        # 第 k 帧在不同位置放一个亮块（模拟挥动的手），并加小噪声
        x0 = 8 * k + 4
        for y in range(8, 24):
            for x in range(x0, min(W, x0 + 12)):
                img[y][x] = [250, 240, 230]
        for y in range(H):
            for x in range(W):
                img[y][x] = [min(255, max(0, c + rnd.randint(-3, 3))) for c in img[y][x]]
        frames.append(img)
    wd = os.path.join(HERE, "work")
    os.makedirs(wd, exist_ok=True)
    with open(os.path.join(wd, "mot_in.hex"), "w") as f:
        for img in frames:
            for row in img:
                for r, g, b in row:
                    f.write(f"{r | g << 8 | b << 16:06x}\n")
    open(os.path.join(wd, "tb_mot.v"), "w").write(TB)
    exe = os.path.join(wd, "tb_mot.vvp")
    subprocess.run([IV, "-g2012", "-o", exe, os.path.join(wd, "tb_mot.v"),
                    os.path.join(HERE, "..", "rtl", "motion_det.v"), os.path.join(HERE, "..", "rtl", "common.v")],
                   check=True)
    subprocess.run([VVP, "-n", exe], cwd=wd, check=True, capture_output=True)
    got = [tuple(int(v) if "x" not in v else -1 for v in l.split()) for l in open(os.path.join(wd, "mot_out.txt"))]
    exp = []
    for k in range(1, NF):
        a, b = blocks(frames[k - 1]), blocks(frames[k])
        c = sx = sy = 0
        for by in range(len(a)):
            for bx in range(len(a[0])):
                if abs(a[by][bx] - b[by][bx]) > TH:
                    c += 1
                    sx += bx
                    sy += by
        exp.append((c, sx, sy))
    ok = got[1:] == exp
    print(f"motion_det：第 2..{NF} 帧 硬件 {got[1:]}，参考 {exp} → {'PASS' if ok else 'FAIL'}")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
