// RAW Bayer → RGB：3x3 分块按颜色平均（去马赛克与 3 倍缩小一步完成）+ 白平衡增益
//   输入：CSI-2 RX 像素流，每拍 4 个 RAW10（p0 在低位：data[9:0] 为最左像素），IW x IH（默认 1920x1440）
//   输出：(IW/3) x (IH/3) RGB（每像素 {B,G,R}，R 在低字节），帧首像素带 o_sof，每拍至多 1 像素
//   块 (bx,by) 覆盖 RAW 行 3by..3by+2、列 3bx..3bx+2；块内对 4 个 Bayer 位置 (行奇偶,列奇偶) 分别求和，
//   各位置样本数 = 行数(1/2) x 列数(1/2)；按 bayer 相位把 4 个位置映射为 R/G/B 后求平均：
//   R、B 除以 1/2/4（移位），G 为两个位置之和除以 4 或 5（x4/5 用 x52429>>16），白平衡后四舍五入
//   帧首：vsync 任一跳变后的第一个有效像素（与 vsync 极性、脉冲/电平形式无关）
//   bayer[1:0]：(0,0) 位置颜色 0=R(RGGB) 1=Gr(GRBG) 2=Gb(GBRG) 3=B(BGGR)
//   gain_r/g/b：8.8 定点白平衡增益（256 = 1.0）
module raw_bin3 #(
    parameter IW = 1920,
    parameter IH = 1440
)(
    input               clk,
    input               rst,
    input               i_vs,
    input               i_valid,
    input  [39:0]       i_data,
    input  [1:0]        bayer,
    input  [11:0]       gain_r,
    input  [11:0]       gain_g,
    input  [11:0]       gain_b,
    output              o_valid,
    output              o_sof,
    output [23:0]       o_data,
    input               o_ready       // 仅用于观测；正常应恒为 1（输入不可反压）
);
    localparam OW  = IW / 3;
    localparam OH  = IH / 3;
    localparam XAW = $clog2(OW / 2 + 1);

    // ---------------- 帧首与坐标 ----------------
    reg        vs_d, armed;
    reg [15:0] x, y;                     // 当前拍首像素坐标（x 为 4 的倍数）
    reg [1:0]  ph;                       // 拍在 12 像素周期中的相位 0..2
    reg [1:0]  ry;                       // 行在块内的序号 0..2
    reg [15:0] by;                       // 块行号
    always @(posedge clk) vs_d <= i_vs;
    wire vs_edge = (i_vs != vs_d);
    wire sof_in  = i_valid && (armed || vs_edge);
    wire [15:0] xi  = sof_in ? 16'd0 : x;
    wire [15:0] yi  = sof_in ? 16'd0 : y;
    wire [1:0]  phi = (sof_in || xi == 0) ? 2'd0 : ph;
    wire [1:0]  ryi = sof_in ? 2'd0 : ry;
    wire [15:0] byi = sof_in ? 16'd0 : by;

    wire [9:0] p0 = i_data[9:0], p1 = i_data[19:10], p2 = i_data[29:20], p3 = i_data[39:30];

    // ---------------- A 级：行内分块求和（按列奇偶分两路）----------------
    // 块内 3 个像素：列奇偶由块起始列决定；sum_e = 偶数列像素和，sum_o = 奇数列像素和
    reg  [10:0] c_e, c_o;               // 跨拍块的已收部分
    reg         a0_v, a1_v;             // 本拍完成的块（最多 2 个：a0 偶数块列、a1 奇数块列）
    reg  [11:0] a0_e, a0_o, a1_e, a1_o;
    reg  [XAW-1:0] a0_x, a1_x;          // 块列在各自存储体中的序号（bx/2）
    reg  [1:0]  a_ry;
    reg         a_rpar;                 // 当前行奇偶
    reg  [15:0] a_by;
    reg         a_sof;
    reg  [15:0] bx;                     // 下一个完成块的块列号
    always @(posedge clk) begin
        if (rst) begin
            armed <= 1'b0; x <= 0; y <= 0; ph <= 0; ry <= 0; by <= 0;
            a0_v <= 0; a1_v <= 0; bx <= 0;
        end else begin
            a0_v <= 1'b0;
            a1_v <= 1'b0;
            if (vs_edge && !i_valid) armed <= 1'b1;
            if (i_valid) begin
                armed <= 1'b0;
                // 坐标推进
                if (xi + 4 >= IW) begin
                    x  <= 0;
                    y  <= yi + 1;
                    ry <= (ryi == 2) ? 2'd0 : ryi + 1'b1;
                    by <= (ryi == 2) ? byi + 1'b1 : byi;
                end else begin
                    x  <= xi + 4;
                    y  <= yi;
                    ry <= ryi;
                    by <= byi;
                end
                ph <= (phi == 2) ? 2'd0 : phi + 1'b1;
                a_ry   <= ryi;
                a_rpar <= yi[0];
                a_by   <= byi;
                a_sof  <= sof_in;
                // 12 像素周期（块 4k..4k+3，起始列 12k、12k+3、12k+6、12k+9）
                case (phi)
                    2'd0: begin   // 块 4k 完成（列 0,1,2：偶奇偶）；块 4k+1 收到列 3（奇）
                        a0_v <= 1'b1; a0_x <= (xi == 0 ? 0 : bx) >> 1;
                        a0_e <= p0 + p2; a0_o <= p1;
                        c_e <= 0; c_o <= p3;
                        bx  <= (xi == 0 ? 16'd0 : bx) + 1'b1;
                    end
                    2'd1: begin   // 块 4k+1 完成（列 3,4,5：奇偶奇）；块 4k+2 收到列 6,7（偶奇）
                        a1_v <= 1'b1; a1_x <= bx >> 1;
                        a1_e <= p0; a1_o <= c_o + p1;
                        c_e <= p2; c_o <= p3;
                        bx  <= bx + 1'b1;
                    end
                    default: begin // 块 4k+2 完成（列 6,7,8：偶奇偶）；块 4k+3 完成（列 9,10,11：奇偶奇）
                        a0_v <= 1'b1; a0_x <= bx >> 1;
                        a0_e <= c_e + p0; a0_o <= c_o;
                        a1_v <= 1'b1; a1_x <= (bx + 1) >> 1;
                        a1_e <= p2; a1_o <= p1 + p3;
                        bx  <= bx + 2'd2;
                    end
                endcase
            end
        end
    end

    // ---------------- B 级：块列累加（偶/奇块列两个存储体，各自读改写）----------------
    // 每个表项 4 个和：{S11, S10, S01, S00}（Sij：行奇偶 i、列奇偶 j），各 12 位
    wire [47:0] q0, q1;
    wire [47:0] n0 = acc_upd(a_ry == 0, a_rpar, q0, a0_e, a0_o);
    wire [47:0] n1 = acc_upd(a_ry == 0, a_rpar, q1, a1_e, a1_o);
    function [47:0] acc_upd(input first, input rpar, input [47:0] q, input [11:0] se, input [11:0] so);
        reg [11:0] s00, s01, s10, s11;
        begin
            {s11, s10, s01, s00} = first ? 48'd0 : q;
            if (!rpar) begin s00 = s00 + se; s01 = s01 + so; end
            else       begin s10 = s10 + se; s11 = s11 + so; end
            acc_upd = {s11, s10, s01, s00};
        end
    endfunction

    // 读地址在输入拍给出（与 A 级同拍），A 级寄存器有效时数据正好就绪
    wire [XAW-1:0] ra0 = ((phi == 0) ? ((xi == 0 ? 0 : bx) >> 1) : (bx >> 1));
    wire [XAW-1:0] ra1 = ((phi == 2) ? ((bx + 1) >> 1) : (bx >> 1));
    sdpram #(.W(48), .D(OW / 2 + 1), .AW(XAW)) u_acc0 (
        .clk(clk), .we(a0_v), .waddr(a0_x), .wdata(n0),
        .re(i_valid && phi != 1), .raddr(ra0), .rdata(q0));
    sdpram #(.W(48), .D(OW / 2 + 1), .AW(XAW)) u_acc1 (
        .clk(clk), .we(a1_v), .waddr(a1_x), .wdata(n1),
        .re(i_valid && phi != 0), .raddr(ra1), .rdata(q1));

    // ---------------- C 级：第 3 行时求平均、映射颜色、白平衡 ----------------
    // 块列奇偶 = 块起始列奇偶；块行奇偶 = 块起始行奇偶
    function [23:0] to_rgb(input [47:0] s, input cpar, input rparb, input [1:0] bay,
                           input [11:0] gr, input [11:0] gg, input [11:0] gb);
        reg [11:0] s00, s01, s10, s11;
        reg [1:0]  rc0, rc1, cc0, cc1;       // 块内偶/奇行数、偶/奇列数
        reg [2:0]  n00, n01, n10, n11;
        reg [11:0] sr, sb; reg [12:0] sg;
        reg [2:0]  nr, nb; reg [3:0] ng;
        reg [29:0] tr, tg, tb, t5;
        reg [19:0] vr, vg, vb;
        begin
            {s11, s10, s01, s00} = s;
            rc0 = rparb ? 2'd1 : 2'd2; rc1 = rparb ? 2'd2 : 2'd1;
            cc0 = cpar  ? 2'd1 : 2'd2; cc1 = cpar  ? 2'd2 : 2'd1;
            n00 = rc0 * cc0; n01 = rc0 * cc1; n10 = rc1 * cc0; n11 = rc1 * cc1;
            case (bay)
                2'd0: begin sr = s00; nr = n00; sb = s11; nb = n11; sg = s01 + s10; ng = n01 + n10; end
                2'd1: begin sr = s01; nr = n01; sb = s10; nb = n10; sg = s00 + s11; ng = n00 + n11; end
                2'd2: begin sr = s10; nr = n10; sb = s01; nb = n01; sg = s00 + s11; ng = n00 + n11; end
                default: begin sr = s11; nr = n11; sb = s00; nb = n00; sg = s01 + s10; ng = n01 + n10; end
            endcase
            // 平均值（RAW10），再 >>2 得 8 位；R/B 样本数为 1/2/4，G 为 4/5
            vr = (nr == 1) ? {sr, 2'b0} : (nr == 2) ? {1'b0, sr, 1'b0} : {2'b0, sr};   // x4/n，保留 2 位小数
            vb = (nb == 1) ? {sb, 2'b0} : (nb == 2) ? {1'b0, sb, 1'b0} : {2'b0, sb};
            t5 = {17'd0, sg} * 30'd52429;                                             // 4*sg/5 = sg*0.8
            vg = (ng == 4) ? {7'd0, sg} : t5[29:16];
            // 均值(10 位, 2 位小数) x 增益(8.8) → 右移 2+2+8 位得 8 位
            tr = vr * gr + (1 << 11); tg = vg * gg + (1 << 11); tb = vb * gb + (1 << 11);
            to_rgb = {sat8(tb >> 12), sat8(tg >> 12), sat8(tr >> 12)};
        end
    endfunction
    function [7:0] sat8(input [29:0] v);
        sat8 = (v > 255) ? 8'd255 : v[7:0];
    endfunction

    // 帧首输出像素：第 0 块行第 0 块（块行最后一行、块列 0）
    wire a_sof_blk = a0_v && (a_ry == 2) && (a_by == 0) && (a0_x == 0);
    reg        c0_v, c1_v, c_sof;
    reg [23:0] c0_d, c1_d;
    always @(posedge clk) begin
        if (rst) begin
            c0_v <= 0; c1_v <= 0;
        end else begin
            c0_v  <= a0_v && (a_ry == 2);
            c1_v  <= a1_v && (a_ry == 2);
            c_sof <= a_sof_blk;
            c0_d  <= to_rgb(n0, 1'b0, a_by[0], bayer, gain_r, gain_g, gain_b);
            c1_d  <= to_rgb(n1, 1'b1, a_by[0], bayer, gain_r, gain_g, gain_b);
        end
    end

    // ---------------- D 级：两个块列 FIFO 交替读出，恢复块列顺序 ----------------
    wire [24:0] f0_d, f1_d;
    wire        f0_v, f1_v;
    reg         sel;                    // 下一个应输出的块列奇偶
    wire        rd0 = o_ready && !sel && f0_v;
    wire        rd1 = o_ready &&  sel && f1_v;
    bfifo #(.W(25), .AW(8)) u_f0 (
        .clk(clk), .rst(rst), .wdata({c_sof, c0_d}), .wvalid(c0_v), .wready(),
        .rdata(f0_d), .rvalid(f0_v), .rready(rd0), .count());
    bfifo #(.W(25), .AW(8)) u_f1 (
        .clk(clk), .rst(rst), .wdata({1'b0, c1_d}), .wvalid(c1_v), .wready(),
        .rdata(f1_d), .rvalid(f1_v), .rready(rd1), .count());
    always @(posedge clk) begin
        if (rst) sel <= 1'b0;
        else if (rd0 || rd1) sel <= ~sel;
    end
    assign o_valid = sel ? f1_v : f0_v;
    assign o_data  = sel ? f1_d[23:0] : f0_d[23:0];
    assign o_sof   = !sel && f0_d[24];
endmodule
