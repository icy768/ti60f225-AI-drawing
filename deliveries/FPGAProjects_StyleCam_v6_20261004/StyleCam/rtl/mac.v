// 乘加阵列
// 数据约定：激活 uint8，权重 int8，乘积有符号；累加器 ACC_W 位有符号
// 输出为逐通道串行节拍：{acc, side, last}，side 为该通道的旁路字节（残差/前传）

// ---------------------------------------------------------------------------
// 稠密卷积（含 1x1）：每个输出像素消耗 NI 个输入字（每字 G 通道），
// 对每个输入字循环 NF=COUT/PE 拍，每拍 PE 个输出通道 x G 个输入通道并行乘加
// 权重 ROM：地址 i*NF+f，位 [(p*G+j)*8 +: 8] = W[f*PE+p][输入字 i 的第 j 个元素]
// SIDE_IN=1 时，输入字附带的 side 字节按通道顺序缓存，作为输出通道 c 的 side（仅 PE=1、NI*G=COUT 的残差 1x1 层）
// ---------------------------------------------------------------------------
module mac_dense #(
    parameter G       = 4,
    parameter NI      = 36,
    parameter COUT    = 24,
    parameter PE      = 4,
    parameter ACC_W   = 26,
    parameter SIDE_IN = 0,
    parameter WFILE   = ""
)(
    input                  clk,
    input                  rst,
    input                  w_we,        // 权重写口（CPU 装载）
    input  [4:0]           w_lane,
    input  [11:0]          w_addr,
    input  [31:0]          w_data,
    input  [G*8-1:0]       i_data,
    input  [G*8-1:0]       i_side,
    input                  i_valid,
    output                 i_ready,
    output [ACC_W-1:0]     o_acc,
    output [7:0]           o_side,
    output                 o_last,
    output                 o_valid,
    input                  o_ready
);
    localparam NF  = COUT / PE;
    localparam WD  = NI * NF;
    localparam WAW = (WD > 1) ? $clog2(WD) : 1;

    // ---- 第 0 级：取数并发出权重地址 ----
    reg  [G*8-1:0]  x0;
    reg             x0_v;
    reg  [15:0]     i0;
    reg  [7:0]      f0;
    wire            s0_fire;
    wire            s0_last_f = (f0 == NF - 1);
    wire            stall;
    assign i_ready  = !stall && (!x0_v || s0_last_f);
    assign s0_fire  = x0_v && !stall;
    wire [WAW-1:0]  waddr = i0 * NF + f0;
    wire [PE*G*8-1:0] wrow;

    wram #(.W(PE * G * 8), .D(WD), .AW(WAW), .INIT(WFILE)) u_w (
        .clk(clk), .we(w_we), .wlane(w_lane), .waddr(w_addr[WAW-1:0]), .wdata(w_data),
        .re(s0_fire), .raddr(waddr), .rdata(wrow)
    );

    always @(posedge clk) begin
        if (rst) begin
            x0_v <= 1'b0;
            i0   <= 0;
            f0   <= 0;
        end else begin
            if (i_valid && i_ready) begin
                x0   <= i_data;
                x0_v <= 1'b1;
                f0   <= 0;
            end else if (s0_fire) begin
                if (s0_last_f) x0_v <= 1'b0;
                else f0 <= f0 + 1'b1;
            end
            if (s0_fire && s0_last_f)
                i0 <= (i0 == NI - 1) ? 0 : i0 + 1'b1;
        end
    end

    // ---- 第 1 级：乘法 ----
    reg  [G*8-1:0]  x1;
    reg             v1, first1, last1;
    reg  [7:0]      f1;
    reg  signed [16:0] prod [0:PE*G-1];
    reg             v2, first2, last2;
    reg  [7:0]      f2;
    integer p, j;

    always @(posedge clk) begin
        if (rst) begin
            v1 <= 1'b0;
            v2 <= 1'b0;
        end else if (!stall) begin
            v1     <= s0_fire;
            x1     <= x0;
            f1     <= f0;
            first1 <= (i0 == 0);
            last1  <= (i0 == NI - 1);
            v2     <= v1;
            f2     <= f1;
            first2 <= first1;
            last2  <= last1;
            for (p = 0; p < PE; p = p + 1)
                for (j = 0; j < G; j = j + 1)
                    prod[p*G+j] <= $signed(wrow[(p*G+j)*8 +: 8]) * $signed({1'b0, x1[j*8 +: 8]});
        end
    end

    // ---- 第 2 级：求和并累加到环形累加器 ----
    reg  signed [ACC_W-1:0] psum [0:PE-1];
    always @(*) begin
        for (p = 0; p < PE; p = p + 1) begin
            psum[p] = 0;
            for (j = 0; j < G; j = j + 1)
                psum[p] = psum[p] + prod[p*G+j];
        end
    end

    // 环形累加器：每个输入字按 f=0..NF-1 依次访问，恰好是长度 NF 的延迟线——
    // 队头 ring[0] 是本拍 f2 的旧值，新值写入队尾，每拍整体前移（无复位、只读队头，可映射 SRL8）
    reg  [PE*ACC_W-1:0] ring [0:NF-1];
    wire [PE*ACC_W-1:0] head = ring[0];
    reg  [PE*ACC_W-1:0] nrow;
    always @(*)
        for (p = 0; p < PE; p = p + 1)
            nrow[p*ACC_W +: ACC_W] = (first2 ? {ACC_W{1'b0}} : head[p*ACC_W +: ACC_W]) + psum[p];
    wire acc_en = v2 && !stall;
    integer k;
    always @(posedge clk)
        if (acc_en) begin
            for (k = 0; k < NF - 1; k = k + 1) ring[k] <= ring[k+1];
            ring[NF-1] <= nrow;
        end

    // 旁路字节（1x1 残差层，要求 PE=1 且 NI*G=COUT）：输入字的 G 个 side 字节按通道顺序进 FIFO，
    // 输出时按通道顺序取用；深度 2*NI 覆盖"当前像素末字输出时，下一像素的前 NI-1 个字已到达"的最坏情况
    wire [G*8-1:0] sd_q;
    wire           sd_pop;
    generate
        if (SIDE_IN) begin : g_sd
            srlfifo #(.W(G * 8), .D(2 * NI)) u_sd (
                .clk(clk), .rst(rst), .din(i_side), .we(i_valid && i_ready),
                .re(sd_pop), .dout(sd_q), .empty(), .full());
        end else begin : g_nsd
            assign sd_q = {(G*8){1'b0}};
        end
    endgenerate
    wire [7:0] sbyte = sd_q[(f2 % G) * 8 +: 8];

    // 输出 FIFO：末字的每一拍产出 PE 个通道终值，入队；读侧逐通道串行输出（深度 NF = 一个像素）
    localparam OW = PE * ACC_W + (SIDE_IN ? 8 : 0);
    wire          of_we = v2 && last2 && !stall;
    wire [OW-1:0] of_d, of_q;
    wire          of_empty, of_full, of_pop;
    generate
        if (SIDE_IN) begin : g_ofs
            assign of_d = {sbyte, nrow};
        end else begin : g_of
            assign of_d = nrow;
        end
    endgenerate
    assign sd_pop = SIDE_IN && of_we && ((f2 % G == G - 1) || (f2 == NF - 1));
    srlfifo #(.W(OW), .D(NF)) u_of (
        .clk(clk), .rst(rst), .din(of_d), .we(of_we), .re(of_pop),
        .dout(of_q), .empty(of_empty), .full(of_full));

    reg  [7:0] ocnt;                    // 输出通道号
    reg  [7:0] pidx;                    // 当前 FIFO 元素内的 PE 序号
    assign o_valid = !of_empty;
    assign o_acc   = of_q[pidx*ACC_W +: ACC_W];
    assign o_side  = SIDE_IN ? of_q[OW-1 -: 8] : 8'd0;
    assign o_last  = (ocnt == COUT - 1);
    assign of_pop  = o_valid && o_ready && (pidx == PE - 1);
    // 输出 FIFO 满且本拍不出队时，末字的节拍停顿
    assign stall   = v2 && last2 && of_full && !of_pop;

    always @(posedge clk) begin
        if (rst) begin
            ocnt <= 0;
            pidx <= 0;
        end else if (o_valid && o_ready) begin
            ocnt <= (ocnt == COUT - 1) ? 0 : ocnt + 1'b1;
            pidx <= (pidx == PE - 1) ? 0 : pidx + 1'b1;
        end
    end
endmodule

// ---------------------------------------------------------------------------
// 深度卷积 3x3：输入为 swg3 输出（组→抽头顺序），每组 9 拍完成 G 个通道
// 权重 ROM：地址 g*9+t，位 [j*8 +: 8] = W[g*G+j][t]
// 中心抽头（t=4）的输入字节作为 side 前传（供后续 1x1 层做残差相加）
// ---------------------------------------------------------------------------
module mac_dw #(
    parameter G     = 4,
    parameter NG    = 6,
    parameter ACC_W = 26,
    parameter WFILE = ""
)(
    input                  clk,
    input                  rst,
    input                  w_we,
    input  [4:0]           w_lane,
    input  [11:0]          w_addr,
    input  [31:0]          w_data,
    input  [G*8-1:0]       i_data,
    input  [3:0]           i_tap,
    input  [7:0]           i_grp,
    input                  i_valid,
    output                 i_ready,
    output [ACC_W-1:0]     o_acc,
    output [7:0]           o_side,
    output                 o_last,
    output                 o_valid,
    input                  o_ready
);
    localparam WD  = NG * 9;
    localparam WAW = $clog2(WD);
    wire stall;
    assign i_ready = !stall;
    wire fire = i_valid && !stall;
    wire [G*8-1:0] wrow;
    wram #(.W(G * 8), .D(WD), .AW(WAW), .INIT(WFILE)) u_w (
        .clk(clk), .we(w_we), .wlane(w_lane), .waddr(w_addr[WAW-1:0]), .wdata(w_data),
        .re(fire), .raddr(i_grp * 9 + i_tap), .rdata(wrow)
    );

    reg [G*8-1:0] x1;
    reg [3:0]     t1, t2;
    reg [7:0]     g1, g2;
    reg           v1, v2;
    reg signed [16:0] prod [0:G-1];
    reg signed [ACC_W-1:0] acc [0:G-1];
    reg [G*8-1:0] ctr;
    integer j;

    // 输出缓存
    reg signed [ACC_W-1:0] obank [0:G-1];
    reg [7:0]              oside [0:G-1];
    reg [7:0]              ocnt, ogrp;
    reg                    obusy;
    wire done_g = v2 && (t2 == 8) && !stall;
    assign stall = v2 && (t2 == 8) && obusy && !(o_ready && ocnt == G - 1);

    always @(posedge clk) begin
        if (rst) begin
            v1 <= 1'b0;
            v2 <= 1'b0;
        end else if (!stall) begin
            v1 <= fire;
            x1 <= i_data;
            t1 <= i_tap;
            g1 <= i_grp;
            v2 <= v1;
            t2 <= t1;
            g2 <= g1;
            for (j = 0; j < G; j = j + 1)
                prod[j] <= $signed(wrow[j*8 +: 8]) * $signed({1'b0, x1[j*8 +: 8]});
            if (v1 && t1 == 4) ctr <= x1;
        end
    end

    always @(posedge clk) begin
        if (v2 && !stall)
            for (j = 0; j < G; j = j + 1)
                acc[j] <= ((t2 == 0) ? 0 : acc[j]) + prod[j];
    end

    assign o_valid = obusy;
    assign o_acc   = obank[ocnt];
    assign o_side  = oside[ocnt];
    assign o_last  = (ocnt == G - 1) && (ogrp == NG - 1);

    always @(posedge clk) begin
        if (rst) begin
            obusy <= 1'b0;
            ocnt  <= 0;
        end else begin
            if (obusy && o_ready) begin
                if (ocnt == G - 1) begin
                    obusy <= 1'b0;
                    ocnt  <= 0;
                end else
                    ocnt <= ocnt + 1'b1;
            end
            if (done_g) begin
                for (j = 0; j < G; j = j + 1) begin
                    obank[j] <= acc[j] + prod[j];
                    oside[j] <= ctr[j*8 +: 8];
                end
                ogrp  <= g2;
                obusy <= 1'b1;
                ocnt  <= 0;
            end
        end
    end
endmodule
