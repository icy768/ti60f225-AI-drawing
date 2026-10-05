// RAW Bayer → RGB（IMX219 用）：2x2 四像素去马赛克（缩小 2 倍）+ 黑电平 + 白平衡 + sRGB gamma
//   输入：CSI-2 RX 像素流，每拍 4 个 RAW10（p0 在低位：data[9:0] 为最左像素），每行 IW 像素
//         IMX219 2x2 模拟合并输出 1280x962 时：IW=1280、IH=960，帧首跳过 skip 行，其余多出的行丢弃，
//         保证每帧恰好输出 (IW/2)x(IH/2) 像素（嵌入数据行若未被 CSI RX 滤掉，令 skip=2 即可跳过）
//   输出：(IW/2)x(IH/2) RGB（每像素 {B,G,R}，R 在低字节），帧首像素带 o_sof，每拍至多 1 像素
//   四像素块 (bx,by) = 有效行 2by、2by+1 与列 2bx、2bx+1；s00/s01 为偶数行的偶/奇列，s10/s11 为奇数行
//   bayer[1:0]：s00 位置颜色 0=R(RGGB) 1=Gr(GRBG) 2=Gb(GBRG) 3=B(BGGR)；IMX219 翻转值 h|v<<1 即为该相位
//   R = s_R - blk，G = s_G1 + s_G2 - 2blk（负数归零），统一为"2 倍均值"后乘 8.8 增益：
//   v10 = min(1023, (2avg * gain + 256) >> 9)；gamma_en=1 时查 sRGB 表（1024→8 位），否则取 v10 >> 2
//   流水：偶数行存入行缓存 → 奇数行读回配对，每拍出 2 像素写入 FIFO → 按 1 像素/拍读出做增益与 gamma
module raw_bin2 #(
    parameter IW    = 1280,
    parameter IH    = 960,
    parameter GAMMA = "gamma_srgb.mem"
)(
    input               clk,
    input               rst,
    input               i_vs,
    input               i_valid,
    input  [39:0]       i_data,
    input  [1:0]        bayer,
    input  [9:0]        blk,
    input  [11:0]       gain_r,
    input  [11:0]       gain_g,
    input  [11:0]       gain_b,
    input               gamma_en,
    input  [1:0]        skip,
    output reg          o_valid,
    output reg          o_sof,
    output reg [23:0]   o_data
);
    localparam NWD = IW / 4;                 // 每行拍数
    localparam XAW = $clog2(NWD);

    // ---------------- 帧首与坐标 ----------------
    // 帧首：vsync 任一跳变后的第一个有效拍（与 vsync 极性、脉冲/电平形式无关）
    reg            vs_d, armed;
    reg [XAW-1:0]  x;                        // 拍在行内的序号
    reg [11:0]     y;                        // 行号（自帧首起，饱和）
    always @(posedge clk) vs_d <= i_vs;
    wire           vs_edge = (i_vs != vs_d);
    wire           sof_in  = i_valid && (armed || vs_edge);
    wire [XAW-1:0] xi = sof_in ? {XAW{1'b0}} : x;
    wire [11:0]    yi = sof_in ? 12'd0 : y;
    wire [11:0]    yl = yi - {10'd0, skip};  // 有效行号
    wire           act  = (yi >= {10'd0, skip}) && (yl < IH);
    wire           ev_w = i_valid && act && !yl[0];
    wire           od_w = i_valid && act &&  yl[0];

    always @(posedge clk) begin
        if (rst) begin
            armed <= 1'b0; x <= 0; y <= 0;
        end else begin
            if (vs_edge && !i_valid) armed <= 1'b1;
            if (i_valid) begin
                armed <= 1'b0;
                if (xi == NWD - 1) begin
                    x <= 0;
                    y <= (yi == 12'hFFF) ? yi : yi + 1'b1;
                end else begin
                    x <= xi + 1'b1;
                    y <= yi;
                end
            end
        end
    end

    // ---------------- 偶数行缓存，奇数行读回 ----------------
    wire [39:0] ev_q;
    sdpram #(.W(40), .D(NWD), .AW(XAW)) u_line (
        .clk(clk), .we(ev_w), .waddr(xi), .wdata(i_data),
        .re(od_w), .raddr(xi), .rdata(ev_q));

    reg        s1_v, s1_sof;
    reg [39:0] s1_o;
    always @(posedge clk) begin
        if (rst) s1_v <= 1'b0;
        else begin
            s1_v   <= od_w;
            s1_o   <= i_data;
            s1_sof <= od_w && (yl == 12'd1) && (xi == 0);
        end
    end

    // 一个四像素块 → {R[9:0], G[10:0], B[9:0]}（未减黑电平）
    function [30:0] quad(input [9:0] s00, input [9:0] s01, input [9:0] s10, input [9:0] s11,
                         input [1:0] bay);
        case (bay)
            2'd0:    quad = {s00, {1'b0, s01} + {1'b0, s10}, s11};
            2'd1:    quad = {s01, {1'b0, s00} + {1'b0, s11}, s10};
            2'd2:    quad = {s10, {1'b0, s00} + {1'b0, s11}, s01};
            default: quad = {s11, {1'b0, s01} + {1'b0, s10}, s00};
        endcase
    endfunction
    wire [30:0] q0 = quad(ev_q[9:0],   ev_q[19:10], s1_o[9:0],   s1_o[19:10], bayer);
    wire [30:0] q1 = quad(ev_q[29:20], ev_q[39:30], s1_o[29:20], s1_o[39:30], bayer);

    // ---------------- 2 像素/拍 → FIFO → 1 像素/拍 ----------------
    // 奇数行每拍出 2 像素，偶数行不出，平均 0.5 像素/拍；FIFO 吸收奇数行的突发（深 256 对）
    wire [62:0] fd;
    wire        fv;
    reg         half;                        // 0：取低位像素 1：取高位像素并出队
    bfifo #(.W(63), .AW(8)) u_fifo (
        .clk(clk), .rst(rst), .wdata({s1_sof, q1, q0}), .wvalid(s1_v), .wready(),
        .rdata(fd), .rvalid(fv), .rready(fv && half), .count());
    always @(posedge clk) begin
        if (rst) half <= 1'b0;
        else if (fv) half <= ~half;
    end
    wire [30:0] px  = half ? fd[61:31] : fd[30:0];
    wire        psof = !half && fd[62];

    // P1：减黑电平，统一为 2 倍均值（11 位）
    wire [9:0]  pr = px[30:21], pb = px[9:0];
    wire [10:0] pg = px[20:10];
    wire [10:0] blk2 = {blk, 1'b0};
    reg         p1_v, p1_sof;
    reg  [10:0] p1_r, p1_g, p1_b;
    always @(posedge clk) begin
        if (rst) p1_v <= 1'b0;
        else begin
            p1_v   <= fv;
            p1_sof <= psof;
            p1_r   <= (pr > blk)  ? {pr - blk, 1'b0} : 11'd0;
            p1_g   <= (pg > blk2) ? pg - blk2        : 11'd0;
            p1_b   <= (pb > blk)  ? {pb - blk, 1'b0} : 11'd0;
        end
    end

    // P2：乘 8.8 增益，四舍五入到 10 位并饱和
    function [9:0] wb(input [10:0] v, input [11:0] g);
        reg [22:0] t;
        begin
            t  = v * g + 23'd256;
            wb = (t[22:9] > 14'd1023) ? 10'd1023 : t[18:9];
        end
    endfunction
    reg        p2_v, p2_sof;
    reg [9:0]  p2_r, p2_g, p2_b;
    always @(posedge clk) begin
        if (rst) p2_v <= 1'b0;
        else begin
            p2_v   <= p1_v;
            p2_sof <= p1_sof;
            p2_r   <= wb(p1_r, gain_r);
            p2_g   <= wb(p1_g, gain_g);
            p2_b   <= wb(p1_b, gain_b);
        end
    end

    // P3：gamma 查表（每通道一块 1024x8 ROM）
    wire [7:0] gr, gg, gb;
    sdpram #(.W(8), .D(1024), .AW(10), .INIT(GAMMA)) u_gr (
        .clk(clk), .we(1'b0), .waddr(10'd0), .wdata(8'd0), .re(1'b1), .raddr(p2_r), .rdata(gr));
    sdpram #(.W(8), .D(1024), .AW(10), .INIT(GAMMA)) u_gg (
        .clk(clk), .we(1'b0), .waddr(10'd0), .wdata(8'd0), .re(1'b1), .raddr(p2_g), .rdata(gg));
    sdpram #(.W(8), .D(1024), .AW(10), .INIT(GAMMA)) u_gb (
        .clk(clk), .we(1'b0), .waddr(10'd0), .wdata(8'd0), .re(1'b1), .raddr(p2_b), .rdata(gb));
    reg        p3_v, p3_sof;
    reg [23:0] p3_lin;
    always @(posedge clk) begin
        if (rst) p3_v <= 1'b0;
        else begin
            p3_v   <= p2_v;
            p3_sof <= p2_sof;
            p3_lin <= {p2_b[9:2], p2_g[9:2], p2_r[9:2]};
        end
    end
    always @(posedge clk) begin
        if (rst) o_valid <= 1'b0;
        else begin
            o_valid <= p3_v;
            o_sof   <= p3_v && p3_sof;
            o_data  <= gamma_en ? {gb, gg, gr} : p3_lin;
        end
    end
endmodule
