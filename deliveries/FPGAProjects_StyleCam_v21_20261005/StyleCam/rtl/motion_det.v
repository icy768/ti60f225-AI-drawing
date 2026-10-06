// 运动检测（挥手手势用）：W x H 像素流 → BS x BS 块平均亮度（W/BS x H/BS）→ 与上一帧逐块比较
//   亮度 y = (R + 2G + B) >> 2；块值 = 块内 y 之和 >> log2(BS*BS)
//   |块值 - 上帧块值| > th 计为运动块；每帧输出运动块数、Σbx、Σby，帧末锁存并给 frame_done 脉冲
// 流水：A 级按块列累加一行内 BS 个像素 → B 级读改写块列累加器（行缓存）→ C 级与上帧块值比较
module motion_det #(
    parameter W  = 640,
    parameter H  = 480,
    parameter BS = 8
)(
    input               clk,
    input               rst,
    input               i_valid,
    input               i_sof,
    input  [23:0]       i_data,      // {B,G,R}
    input  [7:0]        th,
    output reg [15:0]   m_cnt,
    output reg [23:0]   m_sx,
    output reg [23:0]   m_sy,
    output reg          frame_done
);
    localparam BW  = W / BS, BH = H / BS;
    localparam BAW = $clog2(BW * BH);
    localparam XAW = $clog2(BW);
    localparam SH  = $clog2(BS * BS);

    reg  [15:0] x, y;
    wire [15:0] xi = i_sof ? 16'd0 : x;
    wire [15:0] yi = i_sof ? 16'd0 : y;
    wire [9:0]  ys = i_data[7:0] + {i_data[15:8], 1'b0} + i_data[23:16];
    wire [7:0]  y8 = ys[9:2];
    wire [4:0]  xm = xi % BS, ym = yi % BS;

    // ---- A 级：行内水平和 ----
    reg  [12:0] hsum;
    reg         a_v, a_first, a_last;
    reg  [12:0] a_row;
    reg  [XAW-1:0] a_bx;
    reg  [15:0] a_by;
    wire [XAW-1:0] bx_in = xi / BS;
    wire        col_end = i_valid && (xm == BS - 1);
    wire [15:0] acc_q;

    always @(posedge clk) begin
        if (rst) begin
            x <= 0; y <= 0; a_v <= 0;
        end else begin
            a_v <= col_end;
            if (i_valid) begin
                if (xi == W - 1) begin x <= 0; y <= yi + 1; end
                else begin x <= xi + 1; y <= yi; end
                hsum <= (xm == 0) ? {5'd0, y8} : hsum + y8;
                if (xm == BS - 1) begin
                    a_row   <= hsum + y8;
                    a_bx    <= bx_in;
                    a_by    <= yi / BS;
                    a_first <= (ym == 0);
                    a_last  <= (ym == BS - 1);
                end
            end
        end
    end

    // ---- B 级：块列累加器读改写 ----
    wire [15:0] acc_new = a_first ? {3'd0, a_row} : acc_q + a_row;
    sdpram #(.W(16), .D(BW), .AW(XAW)) u_acc (
        .clk(clk), .we(a_v), .waddr(a_bx), .wdata(acc_new),
        .re(col_end), .raddr(bx_in), .rdata(acc_q)
    );
    reg           b_v, b_endf;
    reg [7:0]     b_val;
    reg [BAW-1:0] b_addr;
    reg [XAW-1:0] b_bx;
    reg [15:0]    b_by;
    wire [BAW-1:0] addr_ab = a_by * BW + a_bx;
    wire [7:0]    prev;
    sdpram #(.W(8), .D(BW * BH), .AW(BAW)) u_prev (
        .clk(clk), .we(b_v), .waddr(b_addr), .wdata(b_val),
        .re(a_v && a_last), .raddr(addr_ab), .rdata(prev)
    );
    always @(posedge clk) begin
        if (rst) b_v <= 0;
        else begin
            b_v    <= a_v && a_last;
            b_val  <= acc_new >> SH;
            b_addr <= addr_ab;
            b_bx   <= a_bx;
            b_by   <= a_by;
            b_endf <= (a_bx == BW - 1) && (a_by == BH - 1);
        end
    end

    // ---- C 级：比较与帧统计（b 级数据与本拍读出的上帧值）----
    wire [7:0] d   = (b_val > prev) ? b_val - prev : prev - b_val;
    wire       mov = b_v && (d > th);
    reg [15:0] cnt;
    reg [23:0] sx, sy;
    always @(posedge clk) begin
        if (rst) begin
            cnt <= 0; sx <= 0; sy <= 0; frame_done <= 0;
            m_cnt <= 0; m_sx <= 0; m_sy <= 0;
        end else begin
            frame_done <= 1'b0;
            if (b_v && b_endf) begin
                m_cnt <= cnt + mov;
                m_sx  <= sx + (mov ? b_bx : 0);
                m_sy  <= sy + (mov ? b_by : 0);
                frame_done <= 1'b1;
                cnt <= 0; sx <= 0; sy <= 0;
            end else if (mov) begin
                cnt <= cnt + 1'b1;
                sx  <= sx + b_bx;
                sy  <= sy + b_by;
            end
        end
    end
endmodule
