// 单层卷积引擎：[swg3] → mac_dense / mac_dw → requant
//   K=3：经 3x3 滑窗；K=1：输入字直接进入 1x1 乘加
//   DW=1：深度卷积；FWD=1：前传中心抽头作为 side（供残差 1x1 层）
//   SKIP_ADD=1：1x1 残差层，用输入 side 字节做残差相加
module conv_layer #(
    parameter K        = 3,
    parameter DW       = 0,
    parameter STRIDE   = 1,
    parameter UP       = 0,
    parameter GI       = 4,
    parameter CIN      = 24,
    parameter COUT     = 24,
    parameter G        = 4,
    parameter W        = 160,
    parameter H        = 120,
    parameter PE       = 1,
    parameter ACC_W    = 26,
    parameter R        = 0,
    parameter S        = 16,
    parameter S2       = 8,
    parameter KSK      = 0,
    parameter SKIP_ADD = 0,
    parameter FWD      = 0,
    parameter NSTY     = 4,
    parameter WFILE    = "",
    parameter CFILE    = "",
    parameter LB2      = 1          // 1：stride=1 层用 2 行行缓冲（swg3b），上采样层用 2 行环形
)(
    input               clk,
    input               rst,
    input  [3:0]        style,
    input               cfg_we,
    input               cfg_sel,     // 0：归一化系数 {M,Bq}；1：权重（按 32 位分道）
    input  [4:0]        cfg_lane,
    input  [11:0]       cfg_addr,
    input  [37:0]       cfg_data,
    input  [GI*8-1:0]   i_data,
    input  [GI*8-1:0]   i_side,
    input               i_valid,
    output              i_ready,
    output [G*8-1:0]    o_data,
    output [G*8-1:0]    o_side,
    output              o_valid,
    input               o_ready,
    output              st_v,
    output [18:0]       st_a,
    output [7:0]        st_ch
);
    localparam NGI = CIN / GI;

    wire [ACC_W-1:0] m_acc;
    wire [7:0]       m_side;
    wire             m_last, m_valid, m_ready;

    generate
        if (K == 3) begin : g_k3
            wire [GI*8-1:0] w_data;
            wire [3:0]      w_tap;
            wire [7:0]      w_grp;
            wire            w_valid, w_ready;
            if (LB2 && STRIDE == 1 && !UP) begin : g_lb2
                swg3b #(.G(GI), .NG(NGI), .W(W), .H(H)) u_swg (
                    .clk(clk), .rst(rst),
                    .i_data(i_data), .i_valid(i_valid), .i_ready(i_ready),
                    .o_data(w_data), .o_tap(w_tap), .o_grp(w_grp),
                    .o_valid(w_valid), .o_ready(w_ready));
            end else begin : g_lb3
                swg3 #(.G(GI), .NG(NGI), .W(W), .H(H), .STRIDE(STRIDE), .UP(UP),
                       .NR((LB2 && UP) ? 2 : 3)) u_swg (
                    .clk(clk), .rst(rst),
                    .i_data(i_data), .i_valid(i_valid), .i_ready(i_ready),
                    .o_data(w_data), .o_tap(w_tap), .o_grp(w_grp),
                    .o_valid(w_valid), .o_ready(w_ready));
            end
            if (DW) begin : g_dw
                mac_dw #(.G(GI), .NG(NGI), .ACC_W(ACC_W), .WFILE(WFILE)) u_mac (
                    .clk(clk), .rst(rst),
                    .w_we(cfg_we && cfg_sel), .w_lane(cfg_lane), .w_addr(cfg_addr), .w_data(cfg_data[31:0]),
                    .i_data(w_data), .i_tap(w_tap), .i_grp(w_grp),
                    .i_valid(w_valid), .i_ready(w_ready),
                    .o_acc(m_acc), .o_side(m_side), .o_last(m_last),
                    .o_valid(m_valid), .o_ready(m_ready)
                );
            end else begin : g_dense
                mac_dense #(.G(GI), .NI(NGI * 9), .COUT(COUT), .PE(PE), .ACC_W(ACC_W),
                            .SIDE_IN(0), .WFILE(WFILE)) u_mac (
                    .clk(clk), .rst(rst),
                    .w_we(cfg_we && cfg_sel), .w_lane(cfg_lane), .w_addr(cfg_addr), .w_data(cfg_data[31:0]),
                    .i_data(w_data), .i_side({(GI*8){1'b0}}),
                    .i_valid(w_valid), .i_ready(w_ready),
                    .o_acc(m_acc), .o_side(m_side), .o_last(m_last),
                    .o_valid(m_valid), .o_ready(m_ready)
                );
            end
        end else begin : g_k1
            mac_dense #(.G(GI), .NI(NGI), .COUT(COUT), .PE(PE), .ACC_W(ACC_W),
                        .SIDE_IN(SKIP_ADD), .WFILE(WFILE)) u_mac (
                .clk(clk), .rst(rst),
                .w_we(cfg_we && cfg_sel), .w_lane(cfg_lane), .w_addr(cfg_addr), .w_data(cfg_data[31:0]),
                .i_data(i_data), .i_side(i_side),
                .i_valid(i_valid), .i_ready(i_ready),
                .o_acc(m_acc), .o_side(m_side), .o_last(m_last),
                .o_valid(m_valid), .o_ready(m_ready)
            );
        end
    endgenerate

    requant #(.G(G), .COUT(COUT), .ACC_W(ACC_W), .R(R), .S(S), .S2(S2), .K(KSK),
              .SKIP_ADD(SKIP_ADD), .FWD(FWD), .NSTY(NSTY), .CFILE(CFILE)) u_rq (
        .clk(clk), .rst(rst), .style(style),
        .cfg_we(cfg_we && !cfg_sel), .cfg_addr(cfg_addr[9:0]), .cfg_data(cfg_data),
        .i_acc(m_acc), .i_side(m_side), .i_valid(m_valid), .i_ready(m_ready),
        .o_data(o_data), .o_side(o_side), .o_valid(o_valid), .o_ready(o_ready),
        .st_v(st_v), .st_a(st_a), .st_ch(st_ch)
    );
endmodule

// 末层 12 通道 → PixelShuffle(2) → RGB 光栅输出（宽 2*WL）
// 输入：每个低分辨率位置 3 个字（字 c 的字节 2i+j 为颜色 c 在 (2y+i,2x+j) 的值）
// 偶数行像素直接输出，奇数行像素暂存，一行结束后整行输出
module pixshuf #(
    parameter WL = 320,
    parameter HL = 240
)(
    input               clk,
    input               rst,
    input  [31:0]       i_data,
    input               i_valid,
    output              i_ready,
    output reg [23:0]   o_data,
    output reg          o_valid,
    input               o_ready
);
    localparam D  = 2 * WL;
    localparam AW = $clog2(D);
    reg [1:0]   wi;          // 当前位置已收字数
    reg [31:0]  w0, w1;
    reg [15:0]  x;           // 低分辨率列
    reg         phase;       // 0：接收并输出偶数行；1：输出缓存的奇数行
    reg [AW:0]  rp;
    reg         pend;        // 偶数行第二个像素待输出
    reg [23:0]  pend_px;
    reg [47:0]  odd [0:WL-1];   // 每地址存同一位置的一对奇数行像素，单写口可映射 M10K

    wire out_free = !o_valid || o_ready;
    assign i_ready = !phase && !pend && out_free;
    wire fire = i_valid && i_ready;

    always @(posedge clk) begin
        if (rst) begin
            wi <= 0; x <= 0; phase <= 0; rp <= 0; pend <= 0; o_valid <= 0;
        end else begin
            if (o_valid && o_ready) o_valid <= 1'b0;
            if (fire) begin
                if (wi == 0) begin w0 <= i_data; wi <= 1; end
                else if (wi == 1) begin w1 <= i_data; wi <= 2; end
                else begin
                    wi <= 0;
                    // 字节 b：颜色 c 取 {w2,w1,w0}[c] 的第 b 字节
                    o_data  <= {i_data[7:0],   w1[7:0],   w0[7:0]};
                    o_valid <= 1'b1;
                    pend_px <= {i_data[15:8],  w1[15:8],  w0[15:8]};
                    pend    <= 1'b1;
                    odd[x] <= {i_data[31:24], w1[31:24], w0[31:24],
                               i_data[23:16], w1[23:16], w0[23:16]};
                end
            end else if (pend && out_free) begin
                o_data  <= pend_px;
                o_valid <= 1'b1;
                pend    <= 1'b0;
                if (x == WL - 1) begin
                    x <= 0;
                    phase <= 1'b1;
                    rp <= 0;
                end else
                    x <= x + 1'b1;
            end else if (phase && out_free) begin
                o_data  <= rp[0] ? odd[rp >> 1][47:24] : odd[rp >> 1][23:0];
                o_valid <= 1'b1;
                if (rp == D - 1) phase <= 1'b0;
                rp <= rp + 1'b1;
            end
        end
    end
endmodule
