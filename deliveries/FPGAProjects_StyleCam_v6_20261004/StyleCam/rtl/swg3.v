// 3x3 滑窗生成器（行缓冲 + 取数），通道串行格式
// 输入：按 行→列→通道组 顺序的像素字流，每字 G 个 uint8 通道，每像素 NG 个字
// 输出：对每个输出像素，按 组(g)→抽头(t=ky*3+kx) 顺序输出 NG*9 个字，越界处补零
// 模式：STRIDE=1/2；UP=1 时等效于先最近邻放大 2 倍再做 stride=1 的 3x3 卷积
// 行缓冲为 3 行环形缓冲（BRAM），写侧按读侧进度细粒度放行，读侧等待所需像素写入
module swg3 #(
    parameter G      = 4,
    parameter NG     = 6,
    parameter W      = 160,
    parameter H      = 120,
    parameter STRIDE = 1,
    parameter UP     = 0,
    parameter NR     = 3            // 环形行数；UP=1 时 2 行即可（每个输出行最多用到 2 个输入行）
)(
    input               clk,
    input               rst,
    input  [G*8-1:0]    i_data,
    input               i_valid,
    output              i_ready,
    output [G*8-1:0]    o_data,
    output [3:0]        o_tap,
    output [7:0]        o_grp,
    output              o_valid,
    input               o_ready
);
    localparam WO    = UP ? 2 * W : (W + STRIDE - 1) / STRIDE;
    localparam HO    = UP ? 2 * H : (H + STRIDE - 1) / STRIDE;
    localparam ROWW  = W * NG;
    localparam DEPTH = NR * ROWW;
    localparam AW    = $clog2(DEPTH);

    // ---------------- 读侧状态 ----------------
    reg  signed [17:0] rd_oy, rd_ox;
    reg  [7:0]         rd_g;
    reg  [1:0]         rd_ky, rd_kx;
    reg                rd_done;
    reg  signed [17:0] rbase;      // ky=0 对应的输入行（UP 时为 (oy-1)>>1）
    reg  [1:0]         rbase_slot; // rbase mod NR（rbase=-1 时为 NR-1）
    reg  signed [17:0] cbase;      // 普通：ox*S-1；UP：ox-1（放大域列）

    // ---------------- 写侧状态 ----------------
    reg  [15:0]        wr_row, wr_col;
    reg  [7:0]         wr_grp;
    reg  [AW-1:0]      wr_addr;
    wire               wr_done = (wr_row == H);

    // 写放行：wr_row 覆盖 wr_row-NR 所在槽位，需该行已不再被读侧使用
    wire signed [17:0] r_old   = $signed({2'b0, wr_row}) - NR;
    wire signed [17:0] last_oy = UP ? (2 * r_old + 2) :
                                 (STRIDE == 2 ? ((r_old + 1) >>> 1) : (r_old + 1));
    wire signed [17:0] rd_cmin = UP ? ((rd_ox - 1) >>> 1) : (rd_ox * STRIDE - 1);
    wire wr_ok = (wr_row < NR) || rd_done || (last_oy < rd_oy) ||
                 ((last_oy == rd_oy) && ($signed({2'b0, wr_col}) + 2 < rd_cmin));
    assign i_ready = !wr_done && wr_ok;
    wire wr_fire = i_valid && i_ready;

    // 读放行：当前输出像素所需的最右下输入像素已写完
    wire signed [17:0] rmax_raw = UP ? ((rd_oy + 1) >>> 1) : (rd_oy * STRIDE + 1);
    wire signed [17:0] cmax_raw = UP ? ((rd_ox + 1) >>> 1) : (rd_ox * STRIDE + 1);
    wire signed [17:0] rmax = (rmax_raw > H - 1) ? H - 1 : rmax_raw;
    wire signed [17:0] cmax = (cmax_raw > W - 1) ? W - 1 : cmax_raw;
    wire avail = wr_done || ($signed({2'b0, wr_row}) > rmax) ||
                 (($signed({2'b0, wr_row}) == rmax) && ($signed({2'b0, wr_col}) > cmax));

    // 当前抽头的输入坐标
    wire [1:0] roff = UP ? (rd_oy[0] ? (rd_ky == 2 ? 2'd1 : 2'd0)
                                     : (rd_ky == 0 ? 2'd0 : 2'd1))
                         : rd_ky;
    wire signed [17:0] iy  = rbase + roff;
    wire signed [17:0] uy  = rd_oy + rd_ky - 1;            // UP 时放大域行
    wire signed [17:0] ux  = cbase + rd_kx;                // UP：放大域列；普通：输入列
    wire signed [17:0] ix  = UP ? (ux >>> 1) : ux;
    wire pad = UP ? ((uy < 0) || (uy >= 2 * H) || (ux < 0) || (ux >= 2 * W))
                  : ((iy < 0) || (iy >= H) || (ix < 0) || (ix >= W));
    wire [2:0] slot_sum = rbase_slot + roff;
    wire [1:0] slot = (slot_sum >= NR) ? slot_sum - NR : slot_sum[1:0];
    wire [AW-1:0] rd_addr = slot * ROWW + ix[15:0] * NG + rd_g;

    // 输出 FIFO 与读流水
    wire [3:0] ofc;
    reg        p_valid, p_pad;
    reg [3:0]  p_tap;
    reg [7:0]  p_grp;
    wire       can_issue = !rd_done && avail && (ofc + p_valid < 3);
    wire [G*8-1:0] rdata;

    sdpram #(.W(G * 8), .D(DEPTH), .AW(AW)) u_lb (
        .clk(clk), .we(wr_fire), .waddr(wr_addr), .wdata(i_data),
        .re(can_issue), .raddr(rd_addr), .rdata(rdata)
    );

    sfifo #(.W(G * 8 + 12), .AW(2)) u_of (
        .clk(clk), .rst(rst),
        .i_data({p_grp, p_tap, p_pad ? {(G * 8){1'b0}} : rdata}),
        .i_valid(p_valid), .i_ready(),
        .o_data({o_grp, o_tap, o_data}), .o_valid(o_valid), .o_ready(o_ready),
        .count(ofc[2:0])
    );
    assign ofc[3] = 1'b0;

    // 写侧
    always @(posedge clk) begin
        if (rst || (wr_done && rd_done)) begin
            wr_row  <= 0;
            wr_col  <= 0;
            wr_grp  <= 0;
            wr_addr <= 0;
        end else if (wr_fire) begin
            wr_addr <= (wr_addr == DEPTH - 1) ? 0 : wr_addr + 1'b1;
            if (wr_grp == NG - 1) begin
                wr_grp <= 0;
                if (wr_col == W - 1) begin
                    wr_col <= 0;
                    wr_row <= wr_row + 1'b1;
                end else
                    wr_col <= wr_col + 1'b1;
            end else
                wr_grp <= wr_grp + 1'b1;
        end
    end

    // 读侧
    always @(posedge clk) begin
        p_valid <= can_issue;
        p_pad   <= pad;
        p_tap   <= rd_ky * 3 + rd_kx;
        p_grp   <= rd_g;
        if (rst || (wr_done && rd_done)) begin
            rd_oy <= 0; rd_ox <= 0; rd_g <= 0; rd_ky <= 0; rd_kx <= 0;
            rd_done <= 0;
            rbase <= -18'sd1; rbase_slot <= NR - 1;
            cbase <= -18'sd1;
            p_valid <= 1'b0;
        end else if (can_issue) begin
            if (rd_kx != 2) rd_kx <= rd_kx + 1'b1;
            else begin
                rd_kx <= 0;
                if (rd_ky != 2) rd_ky <= rd_ky + 1'b1;
                else begin
                    rd_ky <= 0;
                    if (rd_g != NG - 1) rd_g <= rd_g + 1'b1;
                    else begin
                        rd_g <= 0;
                        // 下一个输出像素
                        if (rd_ox != WO - 1) begin
                            rd_ox <= rd_ox + 1;
                            cbase <= cbase + (UP ? 1 : STRIDE);
                        end else begin
                            rd_ox <= 0;
                            cbase <= -18'sd1;
                            if (rd_oy == HO - 1) rd_done <= 1'b1;
                            else begin
                                rd_oy <= rd_oy + 1;
                                // 更新 ky=0 行号及其槽位
                                if (UP) begin
                                    // rbase = (oy-1)>>1：当前 oy 为偶数时进入下一行 +1
                                    if (!rd_oy[0]) begin
                                        rbase <= rbase + 1;
                                        rbase_slot <= (rbase_slot == NR - 1) ? 2'd0 : rbase_slot + 1'b1;
                                    end
                                end else begin
                                    rbase <= rbase + STRIDE;
                                    rbase_slot <= (rbase_slot + STRIDE >= NR) ? rbase_slot + STRIDE - NR
                                                                              : rbase_slot + STRIDE;
                                end
                            end
                        end
                    end
                end
            end
        end
    end
endmodule
