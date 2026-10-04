# RTL 生成与逐位验证
#   1) 由整数参数生成各层权重 ROM / 系数 RAM 初始化文件与顶层 stylenet_top.v
#   2) 生成测试平台，iverilog 仿真，与 golden.run 输出逐位比对（含逐层中间结果）
import argparse
import glob
import os
import random
import subprocess

import numpy as np
import torch
from PIL import Image

import golden
from tinystyle import QCfg, TinyStyleNet
from train import DATA, ROOT, image_list

RTL = os.path.join(ROOT, "rtl")
IVERILOG = os.environ.get("IVERILOG", r"C:\iverilog\bin\iverilog.exe")
VVP = os.environ.get("VVP", os.path.join(os.path.dirname(IVERILOG), "vvp.exe"))
G = 4

# 各层并行度（按 640x480、150MHz 估算，见 docs）
# d2 由 12 降到 6：权重行 384→192 位（M10K 20→10 块）、省 24 个乘法器；d2 成为瓶颈，150MHz 约 27fps
PE_TABLE = {"e1": 4, "e2": 4, "d1b": 2, "d2": 6}


def layer_geom(q, W, H):
    # 计算每层输入尺寸与旁路属性
    out, w, h = [], W, H
    L_all = q["layers"]
    for i, L in enumerate(L_all):
        g = dict(W=w, H=h)
        if L["up"]:
            w, h = w * 2, h * 2
        w, h = w // L["stride"], h // L["stride"]
        g["DW"] = int(L["groups"] > 1)
        g["FWD"] = int(g["DW"] and i + 1 < len(L_all) and L_all[i + 1]["skip"] == i - 1)
        g["SKIP_ADD"] = int(L["skip"] is not None)
        g["GI"] = 3 if i == 0 else G
        g["PE"] = 1 if g["DW"] else PE_TABLE.get(L["name"], 1)
        out.append(g)
    return out


def wq_rom(L, gm):
    # 按 mac_dense / mac_dw 的 ROM 布局排列权重
    w = L["wq"]  # [co, ci/groups, k, k]
    cout, k, GI = L["cout"], L["k"], gm["GI"]
    rows = []
    if gm["DW"]:
        for g in range(L["cin"] // GI):
            for t in range(9):
                v = 0
                for j in range(GI):
                    v |= (int(w[g * GI + j, 0, t // 3, t % 3]) & 0xFF) << (8 * j)
                rows.append(v)
        return rows, GI * 8
    PE = gm["PE"]
    NF = cout // PE
    ngi = L["cin"] // GI
    taps = 9 if k == 3 else 1
    for g in range(ngi):
        for t in range(taps):
            for f in range(NF):
                v = 0
                for p in range(PE):
                    for j in range(GI):
                        ky, kx = (t // 3, t % 3) if k == 3 else (0, 0)
                        v |= (int(w[f * PE + p, g * GI + j, ky, kx]) & 0xFF) << (8 * (p * GI + j))
                rows.append(v)
    return rows, PE * GI * 8


def write_mem(path, rows, width):
    nh = (width + 3) // 4
    with open(path, "w") as f:
        for v in rows:
            f.write(f"{v:0{nh}x}\n")


def coef_rows(Ms, Bs):
    # Ms/Bs: 各风格 [COUT] 数组列表 → {M[17:0], Bq[19:0]}
    rows = []
    for M, B in zip(Ms, Bs):
        for m, b in zip(M, B):
            rows.append(((int(m) & 0x3FFFF) << 20) | (int(b) & 0xFFFFF))
    return rows


def generate(q, W, H, outdir, coefs, nsty=4, embed=True, relative_mem=False):
    # coefs[i] = (Ms 列表, Bs 列表)，长度 nsty
    # embed=False：RAM 不带初值，全部由 CPU 经 cfg 总线装载（返回装载脚本）
    os.makedirs(outdir, exist_ok=True)
    script = []
    geo = layer_geom(q, W, H)
    lines = ["// 自动生成：algo/gen_rtl.py，勿手改",
             "module stylenet_top (",
             "    input clk, input rst, input [3:0] style,",
             "    input cfg_we, input cfg_sel, input [4:0] cfg_layer, input [4:0] cfg_lane,",
             "    input [11:0] cfg_addr, input [37:0] cfg_data,",
             "    input [23:0] i_data, input i_valid, output i_ready,",
             "    output [23:0] o_data, output o_valid, input o_ready,",
             "    // IN 统计（分时）：st_sel 选层，st_arm 预备，st_fs/st_fe 帧起止脉冲",
             "    input [4:0] st_sel, input st_arm, input st_fs, input st_fe, input [7:0] st_idx,",
             "    output [39:0] st_s1, output [59:0] st_s2, output st_done, output st_busy",
             ");"]
    n = len(q["layers"])
    for i in range(n):
        lines.append(f"    wire [31:0] d{i}, s{i}; wire v{i}, r{i}; wire sv{i}; wire [18:0] sa{i}; wire [7:0] sc{i};")
    for i, (L, gm) in enumerate(zip(q["layers"], geo)):
        rows, width = wq_rom(L, gm)
        wf = os.path.join(outdir, f"w{i}_{L['name']}.mem").replace("\\", "/")
        write_mem(wf, rows, width)
        cf = os.path.join(outdir, f"c{i}_{L['name']}.mem").replace("\\", "/")
        crow = coef_rows(*coefs[i])
        # 系数 RAM 为 19 位宽、每个系数占两个地址（偶地址低 19 位，奇地址高 19 位），见 requant.v
        write_mem(cf, [h for v in crow for h in (v & 0x7FFFF, v >> 19)], 19)
        if relative_mem:
            wf, cf = os.path.basename(wf), os.path.basename(cf)
        # 装载脚本：权重按 32 位分道，系数整字
        for addr, v in enumerate(rows):
            for lane in range(width // 32):
                script.append((i, 1, lane, addr, (v >> (32 * lane)) & 0xFFFFFFFF))
        for addr, v in enumerate(crow):
            script.append((i, 0, 0, addr, v))
        if not embed:
            wf = cf = ""
        cin_bus = "i_data" if i == 0 else f"d{i-1}"
        side_bus = "24'd0" if i == 0 else f"s{i-1}"
        vin = "i_valid" if i == 0 else f"v{i-1}"
        rin = "i_ready" if i == 0 else f"r{i-1}"
        rout = f"r{i}"
        p = dict(K=L["k"], DW=gm["DW"], STRIDE=L["stride"], UP=int(L["up"]), GI=gm["GI"],
                 CIN=L["cin"], COUT=L["cout"], G=G, W=gm["W"], H=gm["H"], PE=gm["PE"],
                 R=L["R"], S=L["S"], S2=golden.S2, KSK=golden.skip_k(L), SKIP_ADD=gm["SKIP_ADD"],
                 FWD=gm["FWD"], NSTY=nsty)
        ps = ", ".join(f".{k}({v})" for k, v in p.items())
        lines.append(f"    // 第 {i} 层 {L['name']}")
        lines.append(f"    conv_layer #({ps},\n        .WFILE(\"{wf}\"), .CFILE(\"{cf}\")) u_l{i} (")
        lines.append(f"        .clk(clk), .rst(rst), .style(style),")
        lines.append(f"        .cfg_we(cfg_we && cfg_layer == {i}), .cfg_sel(cfg_sel), .cfg_lane(cfg_lane),")
        lines.append(f"        .cfg_addr(cfg_addr), .cfg_data(cfg_data),")
        lines.append(f"        .i_data({cin_bus}), .i_side({side_bus}), .i_valid({vin}), .i_ready({rin}),")
        lines.append(f"        .o_data(d{i}), .o_side(s{i}), .o_valid(v{i}), .o_ready({rout}),")
        lines.append(f"        .st_v(sv{i}), .st_a(sa{i}), .st_ch(sc{i}));")
    # 统计抽头多路选择 + 统计单元
    cmax = max(L["cout"] for L in q["layers"])
    lines.append("    reg tv; reg [18:0] ta; reg [7:0] tc;")
    lines.append("    always @(*) begin")
    lines.append("        tv = 1'b0; ta = 19'd0; tc = 8'd0;")
    lines.append("        case (st_sel)")
    for i in range(n):
        lines.append(f"            5'd{i}: begin tv = sv{i}; ta = sa{i}; tc = sc{i}; end")
    lines.append("            default: ;")
    lines.append("        endcase")
    lines.append("    end")
    lines.append(f"    in_stats #(.CMAX({cmax})) u_st (.clk(clk), .rst(rst), .arm(st_arm), .frame_start(st_fs),")
    lines.append("        .frame_end(st_fe), .i_v(tv), .i_a(ta), .i_ch(tc), .rd_idx(st_idx),")
    lines.append("        .rd_s1(st_s1), .rd_s2(st_s2), .done(st_done), .busy(st_busy));")
    last = n - 1
    lines.append(f"    pixshuf #(.WL({W // 2}), .HL({H // 2})) u_ps (")
    lines.append(f"        .clk(clk), .rst(rst), .i_data(d{last}), .i_valid(v{last}), .i_ready(r{last}),")
    lines.append(f"        .o_data(o_data), .o_valid(o_valid), .o_ready(o_ready));")
    lines.append("endmodule")
    open(os.path.join(outdir, "stylenet_top.v"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    with open(os.path.join(outdir, "cfg.txt"), "w") as f:
        for t in script:
            f.write("%d %d %d %d %x\n" % t)
    return geo, len(script)


TB = r"""`timescale 1ns/1ps
module tb_top;
    parameter W = 32, H = 24, NFR = 1, SEED = 1, RIN = 3, ROUT = 7, LOAD = 0, STL = 0, STC = 24;
    localparam NPX = W * H * NFR;
    reg clk = 0, rst = 1;
    always #5 clk = ~clk;
    reg [23:0] inmem [0:NPX-1];
    initial $readmemh("in.hex", inmem);
    integer ip = 0, op = 0, seed = SEED, f, cyc = 0;
    reg in_v, out_r;
    wire in_r, out_v;
    wire [23:0] out_d;
    reg cw = 0, cs = 0; reg [4:0] cl = 0, cn = 0; reg [11:0] ca = 0; reg [37:0] cd = 0;
    reg loaded = 0;
    reg st_arm = 0, st_fs = 0, st_fe = 0; reg [7:0] st_idx = 0;
    wire [39:0] st_s1; wire [59:0] st_s2; wire st_done, st_busy;
    stylenet_top dut (.clk(clk), .rst(rst), .style(4'd0), .cfg_we(cw), .cfg_sel(cs), .cfg_layer(cl),
        .cfg_lane(cn), .cfg_addr(ca), .cfg_data(cd), .i_data(inmem[ip]), .i_valid(in_v), .i_ready(in_r),
        .o_data(out_d), .o_valid(out_v), .o_ready(out_r),
        .st_sel(STL[4:0]), .st_arm(st_arm), .st_fs(st_fs), .st_fe(st_fe), .st_idx(st_idx),
        .st_s1(st_s1), .st_s2(st_s2), .st_done(st_done), .st_busy(st_busy));
    integer fst, k2;
    // 模拟 CPU 经 cfg 总线装载权重与系数
    integer cf, r, a0, a1, a2, a3; reg [63:0] a4; integer nload = 0;
    initial begin
        if (LOAD) begin
            cf = $fopen("cfg.txt", "r");
            @(negedge rst);
            while (!$feof(cf)) begin
                r = $fscanf(cf, "%d %d %d %d %h", a0, a1, a2, a3, a4);
                if (r == 5) begin
                    @(posedge clk);
                    cw <= 1; cl <= a0; cs <= a1; cn <= a2; ca <= a3; cd <= a4[37:0];
                    @(posedge clk) cw <= 0;     // 相邻写之间空一拍（系数写要两拍；实际 CPU 经 APB 至少隔 6 拍）
                    nload = nload + 1;
                end
            end
            @(posedge clk) cw <= 0;
            @(posedge clk);
            $display("装载 cfg 字数 %0d", nload);
        end
        // 统计：预备并发帧起始脉冲
        wait (!rst);
        @(posedge clk) st_arm <= 1; @(posedge clk) st_arm <= 0; st_fs <= 1; @(posedge clk) st_fs <= 0;
        loaded = 1;
    end
__DUMPS__
    initial begin
        f = $fopen("out.hex", "w");
        in_v = 0; out_r = 0;
        repeat (3) @(posedge clk);
        rst <= 0;
    end
    always @(posedge clk) if (!rst) begin
        cyc <= cyc + 1;
        if (in_v && in_r) ip <= ip + 1;
        if (out_v && out_r) begin
            $fwrite(f, "%h\n", out_d);
            op = op + 1;
        end
        in_v  <= loaded && (((in_v && in_r) ? ip + 1 : ip) < NPX) && (($random(seed) % RIN) == 0);
        out_r <= (($random(seed) % ROUT) != 0);
        if (op == NPX) begin
            $fclose(f);
            st_fe <= 1; @(posedge clk) st_fe <= 0; @(posedge clk);
            fst = $fopen("stats.txt", "w");
            for (k2 = 0; k2 < STC; k2 = k2 + 1) begin
                st_idx <= k2; @(posedge clk); #1;
                $fwrite(fst, "%0d %0d\n", $signed(st_s1), $signed(st_s2));
            end
            $fwrite(fst, "done %0d\n", st_done);
            $fclose(fst);
            $display("DONE cycles=%0d", cyc);
            $finish;
        end
        if (cyc > 200000000) begin
            $display("TIMEOUT ip=%0d op=%0d", ip, op);
            $finish;
        end
    end
endmodule
"""


def make_tb(outdir, n, W, H, nfr, seed, rin, rout, load=0, stl=0, stc=24, bank=0):
    dumps = []
    for i in range(n):
        dumps.append(f"    integer fd{i}; initial fd{i} = $fopen(\"l{i}.hex\", \"w\");")
        dumps.append(f"    always @(posedge clk) if (!rst && dut.v{i} && dut.r{i}) "
                     f"$fwrite(fd{i}, \"%h\\n\", dut.d{i});")
    tb = TB.replace("__DUMPS__", "\n".join(dumps))
    tb = tb.replace(".style(4'd0)", f".style(4'd{bank})")
    tb = tb.replace('in_v  <= loaded', 'in_v  <= (in_v && !in_r) || loaded')
    tb = tb.replace("parameter W = 32, H = 24, NFR = 1, SEED = 1, RIN = 3, ROUT = 7, LOAD = 0, STL = 0, STC = 24",
                    f"parameter W = {W}, H = {H}, NFR = {nfr}, SEED = {seed}, RIN = {rin}, ROUT = {rout}, "
                    f"LOAD = {load}, STL = {stl}, STC = {stc}")
    open(os.path.join(outdir, "tb_top.v"), "w").write(tb)


def simulate(outdir):
    srcs = [os.path.join(outdir, "tb_top.v"), os.path.join(outdir, "stylenet_top.v")] + \
           [os.path.join(RTL, f) for f in ("common.v", "swg3.v", "swg3b.v", "mac.v", "requant.v", "conv_layer.v")]
    exe = os.path.join(outdir, "tb.vvp")
    subprocess.run([IVERILOG, "-g2012", "-o", exe] + srcs, check=True)
    r = subprocess.run([VVP, "-n", exe], cwd=outdir, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", check=True, timeout=1800)
    if "TIMEOUT" in r.stdout or "DONE cycles=" not in r.stdout or "ERROR:" in r.stdout:
        raise RuntimeError(r.stdout + r.stderr)
    return (r.stdout + r.stderr).strip().splitlines()


def read_words(path, width):
    out = []
    for line in open(path):
        line = line.strip()
        if line:
            out.append(int(line, 16) if "x" not in line.lower() else -1)
    return out


def check_layers(outdir, dumps, geo, q):
    # 逐层比对：把 golden 各层 q 按硬件字序（像素→组→通道）展开
    first_bad = None
    for i, (dm, L) in enumerate(zip(dumps, q["layers"])):
        qa = dm["q"]  # [C,H,W]
        C = qa.shape[0]
        exp = []
        for y in range(qa.shape[1]):
            for x in range(qa.shape[2]):
                for g in range(C // G):
                    v = 0
                    for j in range(G):
                        v |= int(qa[g * G + j, y, x]) << (8 * j)
                    exp.append(v)
        got = read_words(os.path.join(outdir, f"l{i}.hex"), 32)
        ok = got == exp
        nbad = sum(1 for a, b in zip(got, exp) if a != b) + abs(len(got) - len(exp))
        print(f"  层 {i:2d} {L['name']:5s} {'OK ' if ok else 'BAD'} words {len(got)}/{len(exp)} mismatch {nbad}")
        if not ok and first_bad is None:
            first_bad = i
    return first_bad


def random_qparams(cfg, imgs, seed=0):
    # 随机初始化网络（仅用于 RTL 逐位测试），先跑观测器得到激活量程
    torch.manual_seed(seed)
    net = TinyStyleNet(**cfg)
    with torch.no_grad():
        for L in net.layers:
            if L.norm is not None:
                L.norm.gamma.uniform_(0.5, 1.5)
                L.norm.beta.uniform_(-0.5, 0.5)
    net.train()
    QCfg.enabled, QCfg.observe = False, True
    x = torch.stack([torch.from_numpy(im).permute(2, 0, 1).float() / 255 for im in imgs])
    with torch.no_grad():
        for _ in range(30):
            for s in range(cfg["n_styles"]):
                net(x, torch.full((x.shape[0],), s, dtype=torch.long))
    path = os.path.join(ROOT, "runs", "_rand", "student.pt")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    torch.save(dict(cfg=net.cfg, styles=[f"s{i}" for i in range(cfg["n_styles"])],
                    sd=net.state_dict(), qat=True), path)
    return golden.export_float(path)


def load_crops(n, W, H, seed=0):
    rnd = random.Random(seed)
    files = sorted(glob.glob(os.path.join(DATA, "val2017", "*.jpg")))
    out = []
    for f in rnd.sample(files, n):
        im = np.asarray(Image.open(f).convert("RGB"))
        y, x = rnd.randint(0, im.shape[0] - H), rnd.randint(0, im.shape[1] - W)
        out.append(np.ascontiguousarray(im[y:y + H, x:x + W]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="", help="已训练检查点目录；为空则用随机网络")
    ap.add_argument("--W", type=int, default=32)
    ap.add_argument("--H", type=int, default=24)
    ap.add_argument("--style", type=int, default=0)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--rin", type=int, default=3, help="输入有效概率 1/rin")
    ap.add_argument("--rout", type=int, default=7, help="输出反压概率 1/rout")
    ap.add_argument("--C", type=int, default=24)
    ap.add_argument("--n_res", type=int, default=4)
    ap.add_argument("--block", default="dw1")
    ap.add_argument("--norm", default="in")
    ap.add_argument("--load_weights", action="store_true", help="RAM 不带初值，由 cfg 总线装载")
    ap.add_argument("--stat_layer", type=int, default=1, help="统计单元比对的层号")
    a = ap.parse_args()

    calib = load_crops(4, 96, 64, seed=a.seed + 100)
    if a.run:
        q = golden.export_float(os.path.join(ROOT, a.run, "student.pt"))
    else:
        cfg = dict(C=a.C, Fc=16, n_res=a.n_res, n_styles=4, norm=a.norm, block=a.block)
        q = random_qparams(cfg, calib, seed=a.seed)
    nsty = len(q["styles"])
    print("标定 R/S:", golden.calibrate(q, calib, nsty))

    img = load_crops(1, a.W, a.H, seed=a.seed)[0]
    y, _, dumps = golden.run(q, img, a.style, dump=True)
    # 系数：测试风格槽位填入本图统计得到的 M/B，其余槽位同样填入（便于切风格测试）
    coefs = []
    nbank = 2 * nsty                      # 每种风格 2 个槽（乒乓），供 CPU 无撕裂更新 IN 系数
    for dm in dumps:
        coefs.append(([dm["M"]] * nbank, [dm["B"]] * nbank))
    outdir = os.path.join(ROOT, "sim", "work", f"top_{a.W}x{a.H}")
    geo, ncfg = generate(q, a.W, a.H, outdir, coefs, nbank, embed=not a.load_weights)
    cout_l = q["layers"][a.stat_layer]["cout"]
    make_tb(outdir, len(q["layers"]), a.W, a.H, 1, a.seed, a.rin, a.rout, int(a.load_weights),
            a.stat_layer, cout_l)
    write_mem(os.path.join(outdir, "in.hex"),
              [int(p[0]) | (int(p[1]) << 8) | (int(p[2]) << 16) for p in img.reshape(-1, 3)], 24)
    log = simulate(outdir)
    print("\n".join(log[-3:]))
    got = read_words(os.path.join(outdir, "out.hex"), 24)
    exp = [int(p[0]) | (int(p[1]) << 8) | (int(p[2]) << 16) for p in y.reshape(-1, 3)]
    ok = got == exp
    print(f"输出 {len(got)}/{len(exp)} 像素，{'逐位一致 PASS' if ok else 'FAIL'}")
    # 统计单元比对：golden 的 Σa、Σa²
    _, st, _ = golden.run(q, img, a.style)
    lines = open(os.path.join(outdir, "stats.txt")).read().splitlines()
    hw = [tuple(int(v) for v in l.split()) for l in lines if l and not l.startswith("done")]
    s1, s2, _ = st[a.stat_layer]
    ok_st = hw == [(int(x), int(y)) for x, y in zip(s1, s2)] and "done 1" in lines
    print(f"IN 统计单元（层 {a.stat_layer} {q['layers'][a.stat_layer]['name']}，{len(hw)} 通道）："
          f"{'逐位一致 PASS' if ok_st else 'FAIL'}；{[l for l in lines if l.startswith('done')]}")
    bad_layer = check_layers(outdir, dumps, geo, q)
    return ok and ok_st and bad_layer is None


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
