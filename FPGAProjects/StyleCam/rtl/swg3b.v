// 3x3 滑窗生成器（stride=1，2 行行缓冲 + 最新行待提交缓冲），接口与 swg3 相同
// 输出像素 (oy,ox) 用输入行 oy-1（上）、oy（中）、oy+1（下）：
//   上、中两行在 BRAM（2 个槽，槽号 = 行号最低位）；下行（最新行）先写入 P 列宽的待提交缓冲（寄存器），
//   读侧用完某列（列 < ox-1）后才把该列提交进 BRAM，覆盖同槽的 oy-1 行
//   第 0 行直接写 BRAM 槽 0；此后每一行都经待提交缓冲
// 与 3 行方案相比 BRAM 省 1/3，代价 P*NG 个字的待提交缓冲
// 待提交缓冲只装当前一行（prow），且按 列*NG+组 的顺序连续写入：做成移位链（每写一个字整体移一位），
// 元素 (col,grp) 的位置 = 本行已写字数 - 1 - (col*NG+grp)；提交读与取窗读各用一条链、按此动态寻址（映射 SRL8）
module swg3b #(
    parameter G  = 4,
    parameter NG = 6,
    parameter W  = 160,
    parameter H  = 120,
    parameter P  = 4            // 待提交列数（2 的幂，>= 4）
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
    localparam ROWW  = W * NG;
    localparam DEPTH = 2 * ROWW;
    localparam AW    = $clog2(DEPTH);
    localparam PD    = P * NG;
    localparam PDW   = $clog2(PD);

    // ---------------- 读侧状态 ----------------
    reg  signed [17:0] rd_oy, rd_ox;
    reg  [7:0]         rd_g;
    reg  [1:0]         rd_ky, rd_kx;
    reg                rd_done;

    // ---------------- 写侧 / 待提交缓冲 ----------------
    reg  [15:0]        wr_row, wr_col;
    reg  [7:0]         wr_grp;
    wire               wr_done = (wr_row == H);
    reg  [G*8-1:0]     pa [0:PD-1];         // 待提交缓冲：提交读用的移位链（pa[0] 最新）
    reg  [G*8-1:0]     pb [0:PD-1];         // 同内容，取窗读用
    reg  [15:0]        pn;                  // prow 已写入缓冲的字数
    reg                pact;                // 缓冲中有未提交完的行
    reg  signed [17:0] prow;                // 缓冲所属行（排空后保留为"最近提交行"，初值 -1）
    reg  [15:0]        pwc;                 // prow 已完整写入缓冲的列数
    reg  [15:0]        cm_col;              // 下一待提交列
    reg  [7:0]         cm_grp;

    wire signed [17:0] rd_cmin = rd_ox - 1;
    wire signed [17:0] cmax_raw = rd_ox + 1;
    wire signed [17:0] cmax = (cmax_raw > W - 1) ? W - 1 : cmax_raw;

    // 提交：该列已完整写入缓冲，且读侧已不再需要（读侧已离开 prow-1 输出行，或列 < ox-1）
    wire signed [17:0] oyb = prow - 1;
    wire rd_free = rd_done || (rd_oy > oyb) || ((rd_oy == oyb) && ($signed({2'b0, cm_col}) < rd_cmin));
    wire commit  = pact && (cm_col < pwc) && rd_free;

    // 写侧放行：第 0 行直写 BRAM（提交占用写口时让行）；其余行写缓冲，需缓冲属于本行（或空闲）且未满
    wire row0    = (wr_row == 0);
    wire pend_ok = pact ? ((prow == $signed({2'b0, wr_row})) && (wr_col - cm_col < P)) : 1'b1;
    assign i_ready = !wr_done && (row0 ? !commit : pend_ok);
    wire wr_fire = i_valid && i_ready;

    // 读放行
    // 行 R（上/中行）在 BRAM 中且列 0..cmax 已就绪；依赖信号全部作为参数传入（保证组合逻辑敏感性）
    function mem_row_ok(input signed [17:0] R, input [15:0] wrow, input [15:0] wcol,
                        input signed [17:0] prw, input pa, input [15:0] cmc, input signed [17:0] cmx);
        begin
            if (R < 0) mem_row_ok = 1'b1;
            else if (R == 0) mem_row_ok = (wrow > 0) || ($signed({2'b0, wcol}) > cmx);
            else mem_row_ok = (prw > R) || ((prw == R) && (!pa || $signed({2'b0, cmc}) > cmx));
        end
    endfunction
    wire signed [17:0] rb = rd_oy + 1;
    wire bot_ok = (rb >= H) || (pact && (prow == rb) && ($signed({2'b0, pwc}) > cmax));
    wire top_ok = mem_row_ok(rd_oy - 1, wr_row, wr_col, prow, pact, cm_col, cmax);
    wire mid_ok = mem_row_ok(rd_oy,     wr_row, wr_col, prow, pact, cm_col, cmax);
    wire avail  = top_ok && mid_ok && bot_ok;

    // 当前抽头
    wire signed [17:0] iy = rd_oy + rd_ky - 1;
    wire signed [17:0] ix = rd_ox + rd_kx - 1;
    wire pad = (iy < 0) || (iy >= H) || (ix < 0) || (ix >= W);
    wire from_pend = (rd_ky == 2);
    wire [AW-1:0] rd_addr = iy[0] * ROWW + ix[15:0] * NG + rd_g;
    // 待提交缓冲的链上位置（只在实际使用时有效：提交时 / 取窗读下行且不补零时）
    wire [15:0] pos_t = pn - 1'b1 - (ix[15:0] * NG + rd_g);
    wire [15:0] pos_c = pn - 1'b1 - (cm_col * NG + cm_grp);

    // BRAM：写口在提交与第 0 行直写间复用
    wire [AW-1:0] waddr = commit ? (prow[0] * ROWW + cm_col * NG + cm_grp)
                                 : (wr_col * NG + wr_grp);
    wire [G*8-1:0] wdata = commit ? pa[pos_c[PDW-1:0]] : i_data;
    wire we = commit || (wr_fire && row0);

    wire [3:0] ofc;
    reg        p_valid, p_pad, p_src;
    reg [3:0]  p_tap;
    reg [7:0]  p_grp;
    reg [G*8-1:0] p_pdata;
    wire       can_issue = !rd_done && avail && (ofc + p_valid < 3);
    wire [G*8-1:0] rdata;
    sdpram #(.W(G * 8), .D(DEPTH), .AW(AW)) u_lb (
        .clk(clk), .we(we), .waddr(waddr), .wdata(wdata),
        .re(can_issue && !from_pend), .raddr(rd_addr), .rdata(rdata)
    );
    sfifo #(.W(G * 8 + 12), .AW(2)) u_of (
        .clk(clk), .rst(rst),
        .i_data({p_grp, p_tap, p_pad ? {(G * 8){1'b0}} : (p_src ? p_pdata : rdata)}),
        .i_valid(p_valid), .i_ready(),
        .o_data({o_grp, o_tap, o_data}), .o_valid(o_valid), .o_ready(o_ready),
        .count(ofc[2:0])
    );
    assign ofc[3] = 1'b0;

    wire frame_end = wr_done && rd_done && !pact;

    // 待提交缓冲移位链（无复位，映射 SRL8）
    wire pwr = wr_fire && !row0;
    integer k;
    always @(posedge clk)
        if (pwr) begin
            pa[0] <= i_data;
            pb[0] <= i_data;
            for (k = 1; k < PD; k = k + 1) begin
                pa[k] <= pa[k-1];
                pb[k] <= pb[k-1];
            end
        end

    // 写侧与提交
    always @(posedge clk) begin
        if (rst || frame_end) begin
            wr_row <= 0; wr_col <= 0; wr_grp <= 0; pn <= 0;
            pact <= 1'b0; prow <= -18'sd1; pwc <= 0; cm_col <= 0; cm_grp <= 0;
        end else begin
            if (commit) begin
                if (cm_grp == NG - 1) begin
                    cm_grp <= 0;
                    if (cm_col == W - 1) begin
                        cm_col <= 0;
                        pact   <= 1'b0;          // 本行提交完毕（prow 保留）
                    end else
                        cm_col <= cm_col + 1'b1;
                end else
                    cm_grp <= cm_grp + 1'b1;
            end
            if (wr_fire) begin
                if (!row0) begin
                    if (!pact || prow != $signed({2'b0, wr_row})) begin
                        // 新行进入缓冲
                        pact <= 1'b1;
                        prow <= $signed({2'b0, wr_row});
                        pwc  <= 0;
                        pn   <= 1;
                        cm_col <= 0;
                        cm_grp <= 0;
                    end else
                        pn <= pn + 1'b1;
                    if (wr_grp == NG - 1) pwc <= wr_col + 1'b1;
                end
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
    end

    // 读侧
    always @(posedge clk) begin
        p_valid <= can_issue;
        p_pad   <= pad;
        p_src   <= from_pend;
        p_pdata <= pb[pos_t[PDW-1:0]];
        p_tap   <= rd_ky * 3 + rd_kx;
        p_grp   <= rd_g;
        if (rst || frame_end) begin
            rd_oy <= 0; rd_ox <= 0; rd_g <= 0; rd_ky <= 0; rd_kx <= 0;
            rd_done <= 0;
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
                        if (rd_ox != W - 1) rd_ox <= rd_ox + 1;
                        else begin
                            rd_ox <= 0;
                            if (rd_oy == H - 1) rd_done <= 1'b1;
                            else rd_oy <= rd_oy + 1;
                        end
                    end
                end
            end
        end
    end
endmodule
