`timescale 1ns/1ps
module tb_top;
    parameter W = 640, H = 480, NFR = 1, SEED = 19, RIN = 3, ROUT = 7, LOAD = 1, STL = 10, STC = 24;
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
    stylenet_top dut (.clk(clk), .rst(rst), .style(4'd1), .cfg_we(cw), .cfg_sel(cs), .cfg_layer(cl),
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
    integer fd0; initial fd0 = $fopen("l0.hex", "w");
    always @(posedge clk) if (!rst && dut.v0 && dut.r0) $fwrite(fd0, "%h\n", dut.d0);
    integer fd1; initial fd1 = $fopen("l1.hex", "w");
    always @(posedge clk) if (!rst && dut.v1 && dut.r1) $fwrite(fd1, "%h\n", dut.d1);
    integer fd2; initial fd2 = $fopen("l2.hex", "w");
    always @(posedge clk) if (!rst && dut.v2 && dut.r2) $fwrite(fd2, "%h\n", dut.d2);
    integer fd3; initial fd3 = $fopen("l3.hex", "w");
    always @(posedge clk) if (!rst && dut.v3 && dut.r3) $fwrite(fd3, "%h\n", dut.d3);
    integer fd4; initial fd4 = $fopen("l4.hex", "w");
    always @(posedge clk) if (!rst && dut.v4 && dut.r4) $fwrite(fd4, "%h\n", dut.d4);
    integer fd5; initial fd5 = $fopen("l5.hex", "w");
    always @(posedge clk) if (!rst && dut.v5 && dut.r5) $fwrite(fd5, "%h\n", dut.d5);
    integer fd6; initial fd6 = $fopen("l6.hex", "w");
    always @(posedge clk) if (!rst && dut.v6 && dut.r6) $fwrite(fd6, "%h\n", dut.d6);
    integer fd7; initial fd7 = $fopen("l7.hex", "w");
    always @(posedge clk) if (!rst && dut.v7 && dut.r7) $fwrite(fd7, "%h\n", dut.d7);
    integer fd8; initial fd8 = $fopen("l8.hex", "w");
    always @(posedge clk) if (!rst && dut.v8 && dut.r8) $fwrite(fd8, "%h\n", dut.d8);
    integer fd9; initial fd9 = $fopen("l9.hex", "w");
    always @(posedge clk) if (!rst && dut.v9 && dut.r9) $fwrite(fd9, "%h\n", dut.d9);
    integer fd10; initial fd10 = $fopen("l10.hex", "w");
    always @(posedge clk) if (!rst && dut.v10 && dut.r10) $fwrite(fd10, "%h\n", dut.d10);
    integer fd11; initial fd11 = $fopen("l11.hex", "w");
    always @(posedge clk) if (!rst && dut.v11 && dut.r11) $fwrite(fd11, "%h\n", dut.d11);
    integer fd12; initial fd12 = $fopen("l12.hex", "w");
    always @(posedge clk) if (!rst && dut.v12 && dut.r12) $fwrite(fd12, "%h\n", dut.d12);
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
        in_v  <= (in_v && !in_r) || loaded && (((in_v && in_r) ? ip + 1 : ip) < NPX) && (($random(seed) % RIN) == 0);
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
