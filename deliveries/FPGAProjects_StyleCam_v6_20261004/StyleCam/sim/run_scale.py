# cam_scale3 单元测试：随机图像（2 帧）→ iverilog → 与 Python 参考逐像素比对
import os
import random
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
IV = os.environ.get("IVERILOG", r"C:\iverilog\bin\iverilog.exe")
VVP = os.environ.get("VVP", os.path.join(os.path.dirname(IV), "vvp.exe"))

TB = r"""`timescale 1ns/1ps
module tb;
    parameter IW = 24, IH = 9, XOFF = 6, CW = 12, NFR = 2, NW = IW / 2 * IH * NFR;
    reg clk = 0, rst = 1;
    always #5 clk = ~clk;
    reg [47:0] mem [0:NW-1];
    initial $readmemh("scale_in.hex", mem);
    integer ip = 0, seed = 5, f, n = 0;
    reg v, sof;
    reg [47:0] d;
    wire ov, osof;
    wire [23:0] od;
    cam_scale3 #(.IW(IW), .IH(IH), .XOFF(XOFF), .CW(CW)) dut (
        .clk(clk), .rst(rst), .i_valid(v), .i_sof(sof), .i_data(d),
        .o_valid(ov), .o_sof(osof), .o_data(od));
    initial begin
        f = $fopen("scale_out.txt", "w");
        v = 0; sof = 0;
        repeat (3) @(posedge clk);
        rst <= 0;
    end
    always @(posedge clk) if (!rst) begin
        if (ov) begin $fwrite(f, "%h %0d\n", od, osof); n = n + 1; end
        if (ip < NW && ($random(seed) & 1)) begin
            v <= 1; d <= mem[ip]; sof <= (ip % (IW / 2 * IH)) == 0; ip <= ip + 1;
        end else begin
            v <= 0; sof <= 0;
        end
        if (ip == NW && !v) begin
            repeat (8) @(posedge clk);
            $fclose(f);
            $finish;
        end
    end
endmodule
"""


def ref(img, IW, IH, XOFF, CW):
    out = []
    for oy in range(IH // 3):
        for ox in range(CW // 3):
            px = [0, 0, 0]
            for dy in range(3):
                for dx in range(3):
                    p = img[oy * 3 + dy][XOFF + ox * 3 + dx]
                    for c in range(3):
                        px[c] += p[c]
            q = [((s * 7282 + 32768) >> 16) & 0xFF for s in px]
            out.append((q[0] | (q[1] << 8) | (q[2] << 16), int(oy == 0 and ox == 0)))
    return out


def main():
    IW, IH, XOFF, CW, NFR = 24, 9, 6, 12, 2
    rnd = random.Random(1)
    frames = [[[[rnd.randrange(256) for _ in range(3)] for _ in range(IW)] for _ in range(IH)] for _ in range(NFR)]
    frames[0][0][XOFF] = [255, 255, 255]
    for y in range(3):
        for x in range(3):
            frames[1][y][XOFF + x] = [255, 255, 255]   # 全 255 块检查饱和
    wd = os.path.join(HERE, "work")
    os.makedirs(wd, exist_ok=True)
    with open(os.path.join(wd, "scale_in.hex"), "w") as f:
        for img in frames:
            for row in img:
                for x in range(0, IW, 2):
                    p0, p1 = row[x], row[x + 1]
                    w = sum(v << (8 * i) for i, v in enumerate(p0 + p1))
                    f.write(f"{w:012x}\n")
    open(os.path.join(wd, "tb_scale.v"), "w").write(TB)
    exe = os.path.join(wd, "tb_scale.vvp")
    subprocess.run([IV, "-g2012", "-o", exe, os.path.join(wd, "tb_scale.v"),
                    os.path.join(HERE, "..", "rtl", "cam_scale3.v"), os.path.join(HERE, "..", "rtl", "common.v")],
                   check=True)
    subprocess.run([VVP, "-n", exe], cwd=wd, check=True, capture_output=True)
    got = [(int(a, 16), int(b)) for a, b in (l.split() for l in open(os.path.join(wd, "scale_out.txt")))]
    exp = sum((ref(img, IW, IH, XOFF, CW) for img in frames), [])
    ok = got == exp
    print(f"cam_scale3：{len(got)}/{len(exp)} 像素，{'PASS' if ok else 'FAIL'}")
    if not ok:
        for i, (g, e) in enumerate(zip(got, exp)):
            if g != e:
                print("  首个不一致", i, hex(g[0]), g[1], hex(e[0]), e[1])
                break
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
