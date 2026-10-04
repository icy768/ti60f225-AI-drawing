// 逐通道反量化 + 归一化仿射 + 残差 + 截断（与 golden.py 逐位一致）
//   a = sat19(acc >>> R)
//   t = a*M[c] + (Bq[c] <<< (S-S2)) + (SKIP_ADD ? side*K : 0)
//   q = clip(t >>> S, 0, 255)
// 系数 {M[17:0], Bq[19:0]}（38 位），第 k 个系数（k=style*COUT+c）拆成两个 19 位半字存在地址 2k（低）、2k+1（高）：
//   存储体 19 位宽只占 1 块 M10K（38 位宽要 2 块）；代价是每个通道节拍占 2 拍（先读高半字、再读低半字），
//   各层每像素计算周期都 ≥ 2*COUT，吞吐不受影响。CPU 经 cfg 口写整个 38 位系数：当拍写高半字、下一拍写低半字，
//   故相邻两次 cfg 写须至少间隔一拍（CPU 经 APB 写 3 个寄存器才触发一次，实际间隔 ≥6 拍）
// 输出按 G 通道打包成字；FWD=1 时 side 字节随数据一并打包前传
module requant #(
    parameter G        = 4,
    parameter COUT     = 24,
    parameter ACC_W    = 26,
    parameter R        = 0,
    parameter S        = 16,
    parameter S2       = 8,
    parameter K        = 0,
    parameter SKIP_ADD = 0,
    parameter FWD      = 0,
    parameter NSTY     = 4,
    parameter CFILE    = ""
)(
    input                  clk,
    input                  rst,
    input  [3:0]           style,
    // 系数写口
    input                  cfg_we,
    input  [9:0]           cfg_addr,
    input  [37:0]          cfg_data,
    // 输入节拍
    input  [ACC_W-1:0]     i_acc,
    input  [7:0]           i_side,
    input                  i_valid,
    output                 i_ready,
    // 输出字
    output reg [G*8-1:0]   o_data,
    output reg [G*8-1:0]   o_side,
    output reg             o_valid,
    input                  o_ready,
    // IN 统计抽头：每个通道值 a（移位饱和后）与通道号
    output                 st_v,
    output [18:0]          st_a,
    output [7:0]           st_ch
);
    localparam CD  = NSTY * COUT;
    localparam CAW = (CD > 1) ? $clog2(CD) : 1;
    localparam signed [18:0] AMAX = 19'sd262143;
    localparam signed [18:0] AMIN = -19'sd262144;

    wire en;
    reg  ph;                            // 1：当前节拍的第二拍（读低半字），不接收新节拍
    wire fire = i_valid && en && !ph;
    assign i_ready = en && !ph;

    reg [7:0] ch;
    assign st_v  = fire;
    assign st_ch = ch;

    // 系数写：高半字当拍写，低半字下一拍写
    reg            wlo_p;
    reg [CAW-1:0]  wlo_a;
    reg [18:0]     wlo_d;
    always @(posedge clk) begin
        if (rst) wlo_p <= 1'b0;
        else     wlo_p <= cfg_we;
        if (cfg_we) begin
            wlo_a <= cfg_addr[CAW-1:0];
            wlo_d <= cfg_data[18:0];
        end
    end
    wire          c_we    = cfg_we || wlo_p;
    wire [CAW:0]  c_waddr = cfg_we ? {cfg_addr[CAW-1:0], 1'b1} : {wlo_a, 1'b0};
    wire [18:0]   c_wdata = cfg_we ? cfg_data[37:19] : wlo_d;
    // 系数读：接收节拍时读高半字并锁存地址，下一拍按锁存地址读低半字（style 在两拍间变化也取自同一槽）
    reg  [CAW-1:0] ra_q;
    wire [CAW-1:0] ra_hi   = style * COUT + ch;
    wire [CAW:0]   c_raddr = ph ? {ra_q, 1'b0} : {ra_hi, 1'b1};
    wire [18:0]    c_q;
    sdpram #(.W(19), .D(2 * CD), .AW(CAW + 1), .INIT(CFILE)) u_c (
        .clk(clk), .we(c_we), .waddr(c_waddr), .wdata(c_wdata),
        .re(fire || (ph && en)), .raddr(c_raddr), .rdata(c_q)
    );
    reg  [18:0] c_hi;
    wire [37:0] coef = {c_hi, c_q};

    // 第 0 级：移位饱和
    wire signed [ACC_W-1:0] acc_s = i_acc;
    wire signed [ACC_W-1:0] sh    = acc_s >>> R;
    wire signed [18:0] a0 = (sh > AMAX) ? AMAX : ((sh < AMIN) ? AMIN : sh[18:0]);
    assign st_a = a0;

    reg               v1, v1b, v2, v3;
    reg signed [18:0] a1, a1b;
    reg [7:0]         s1, s1b, s2, s3;
    reg [7:0]         c1, c1b, c2, c3;
    // 中间和位宽 40：|a*M| < 2^35（a 19 位、M 18 位），|Bq<<<(S-S2)| < 2^34（S≤23），|side*K| < 2^25 → 和 < 2^36，不溢出
    reg signed [39:0] p2, b2, k2, t3;

    wire signed [17:0] M  = coef[37:20];
    wire signed [19:0] Bq = coef[19:0];

    always @(posedge clk) begin
        if (rst) begin
            v1 <= 0; v1b <= 0; v2 <= 0; v3 <= 0;
            ch <= 0; ph <= 0;
        end else if (en) begin
            ph <= fire;
            if (fire) ra_q <= ra_hi;
            // 第 0→1 级
            v1 <= fire;
            a1 <= a0;
            s1 <= i_side;
            c1 <= ch;
            if (fire) ch <= (ch == COUT - 1) ? 0 : ch + 1'b1;
            // 第 1→1b 级：锁存高半字（低半字在本拍读出）
            v1b  <= v1;
            a1b  <= a1;
            s1b  <= s1;
            c1b  <= c1;
            c_hi <= c_q;
            // 第 1b→2 级：乘法、偏置对齐、残差项
            v2 <= v1b;
            p2 <= a1b * M;
            b2 <= $signed(Bq) <<< (S - S2);
            k2 <= SKIP_ADD ? $signed({1'b0, s1b}) * K : 40'sd0;
            s2 <= s1b;
            c2 <= c1b;
            // 第 2→3 级：求和
            v3 <= v2;
            t3 <= p2 + b2 + k2;
            s3 <= s2;
            c3 <= c2;
        end
    end

    // 第 3 级：截断并打包
    wire signed [39:0] tq = t3 >>> S;
    wire [7:0] q = (tq < 0) ? 8'd0 : ((tq > 255) ? 8'd255 : tq[7:0]);
    wire [7:0] lane = c3 % G;
    wire word_done = v3 && (lane == G - 1);
    assign en = !(word_done && o_valid && !o_ready);

    // 前 G-1 个字节暂存，第 G 个字节到达时与暂存内容一起输出
    reg [G*8-1:0] pk_d, pk_s;
    wire [7:0] sfw = FWD ? s3 : 8'd0;
    always @(posedge clk) begin
        if (rst) begin
            o_valid <= 1'b0;
        end else begin
            if (o_valid && o_ready) o_valid <= 1'b0;
            if (v3 && en) begin
                pk_d[lane*8 +: 8] <= q;
                pk_s[lane*8 +: 8] <= sfw;
                if (word_done) begin
                    o_data  <= {q, pk_d[(G-1)*8-1:0]};
                    o_side  <= {sfw, pk_s[(G-1)*8-1:0]};
                    o_valid <= 1'b1;
                end
            end
        end
    end
endmodule
