`timescale 1ns/1ps
// swg3 单元测试：随机输入停顿 + 随机输出反压，逐字记录输出
module tb_swg3;
    parameter G = 4, NG = 2, W = 7, H = 5, STRIDE = 1, UP = 0, NFRAMES = 2, SEED = 1, NR = 3, B2 = 0;
    localparam WO   = UP ? 2 * W : (W + STRIDE - 1) / STRIDE;
    localparam HO   = UP ? 2 * H : (H + STRIDE - 1) / STRIDE;
    localparam NIN  = W * H * NG * NFRAMES;
    localparam NOUT = WO * HO * NG * 9 * NFRAMES;

    reg clk = 0, rst = 1;
    always #5 clk = ~clk;

    reg [G*8-1:0] inmem [0:NIN-1];
    initial $readmemh("swg_in.hex", inmem);

    integer ip = 0, op = 0, seed = SEED, f, cyc = 0;
    reg in_v, out_r;
    wire in_r, out_v;
    wire [G*8-1:0] out_d;
    wire [3:0] out_t;
    wire [7:0] out_g;

    generate if (B2) begin : g_b
        swg3b #(.G(G), .NG(NG), .W(W), .H(H)) dut (
            .clk(clk), .rst(rst),
            .i_data(inmem[ip]), .i_valid(in_v), .i_ready(in_r),
            .o_data(out_d), .o_tap(out_t), .o_grp(out_g), .o_valid(out_v), .o_ready(out_r));
    end else begin : g_a
        swg3 #(.G(G), .NG(NG), .W(W), .H(H), .STRIDE(STRIDE), .UP(UP), .NR(NR)) dut (
            .clk(clk), .rst(rst),
            .i_data(inmem[ip]), .i_valid(in_v), .i_ready(in_r),
            .o_data(out_d), .o_tap(out_t), .o_grp(out_g), .o_valid(out_v), .o_ready(out_r));
    end endgenerate

    initial begin
        f = $fopen("swg_out.txt", "w");
        in_v = 0; out_r = 0;
        repeat (3) @(posedge clk);
        rst <= 0;
    end

    always @(posedge clk) if (!rst) begin
        cyc <= cyc + 1;
        if (in_v && in_r) ip <= ip + 1;
        if (out_v && out_r) begin
            $fwrite(f, "%h %0d %0d\n", out_d, out_t, out_g);
            op = op + 1;
        end
        in_v  <= (((in_v && in_r) ? ip + 1 : ip) < NIN) && (($random(seed) & 3) != 0);
        out_r <= (($random(seed) & 7) != 0);
        if (op == NOUT) begin
            $fclose(f);
            $display("DONE cycles=%0d", cyc);
            $finish;
        end
        if (cyc > 2000000) begin
            $display("TIMEOUT ip=%0d op=%0d", ip, op);
            $finish;
        end
    end
endmodule
