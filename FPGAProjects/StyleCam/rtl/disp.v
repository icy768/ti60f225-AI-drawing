// HDMI 显示：视频时序 + 画面合成 + OSD 文字叠加（像素时钟域）
// 模式 0：左原图、右风格图并排（各 VW x VH，纵向起点 VY0）
// 模式 1/2：风格图 / 原图 1.5 倍全屏（VW*1.5 x VH*1.5 居中）
// 视频数据由 DDR 取数模块按行推入 FIFO：模式 0 每行 VW 个原图 + VW 个风格图像素；模式 1/2 每行 VW 个
// 行请求：提前 2 行发出，经小异步 FIFO 送至 AXI 时钟域；场消隐开始时发帧请求，随后若干行内清空残留数据
// OSD：文字 RAM（CPU 写，双时钟）+ 8x16 字库，按 SC 倍放大；字符码 0 透明，bit7 选黄色

// 双时钟简单双口 RAM
module dcram #(
    parameter W    = 8,
    parameter D    = 2048,
    parameter AW   = 11,
    parameter INIT = ""
)(
    input               wclk,
    input               we,
    input  [AW-1:0]     waddr,
    input  [W-1:0]      wdata,
    input               rclk,
    input  [AW-1:0]     raddr,
    output reg [W-1:0]  rdata
);
    reg [W-1:0] mem [0:D-1];
    integer k;
    initial begin
        for (k = 0; k < D; k = k + 1) mem[k] = 0;
        if (INIT != "") $readmemh(INIT, mem);
    end
    always @(posedge wclk) if (we) mem[waddr] <= wdata;
    always @(posedge rclk) rdata <= mem[raddr];
endmodule

module disp_core #(
    parameter H_ACT = 1280, H_FP = 110, H_SYNC = 40, H_BP = 220,
    parameter V_ACT = 720,  V_FP = 5,   V_SYNC = 5,  V_BP = 20,
    parameter VW = 640, VH = 480, VY0 = 120,
    parameter SC = 2,                       // OSD 放大倍数
    parameter FONT = "font8x16.mem"
)(
    input               clk,                // 像素时钟
    input               rst,
    input  [1:0]        mode,               // 帧起始时锁存
    // 行请求（去往 AXI 域）：{type, line}，type=1 帧请求
    output reg [11:0]   req_data,
    output reg          req_valid,
    // 视频 FIFO（首字直通）
    input  [23:0]       f_data,
    input               f_valid,
    output reg          f_ready,
    // OSD 文字 RAM 写口（CPU 时钟域）
    input               osd_clk,
    input               osd_we,
    input  [10:0]       osd_addr,
    input  [7:0]        osd_data,
    // 视频输出
    output reg          o_hs,
    output reg          o_vs,
    output reg          o_de,
    output reg [7:0]    o_r,
    output reg [7:0]    o_g,
    output reg [7:0]    o_b,
    output reg [15:0]   underflow,
    output reg          frame_pulse
);
    localparam H_TOT = H_ACT + H_FP + H_SYNC + H_BP;
    localparam V_TOT = V_ACT + V_FP + V_SYNC + V_BP;
    localparam CW = 8 * SC, CH = 16 * SC;
    localparam COLS = H_ACT / CW;
    localparam FW = VW * 3 / 2, FH = VH * 3 / 2;
    localparam FX0 = (H_ACT - FW) / 2, FY0 = (V_ACT - FH) / 2;

    reg [15:0] hc, vc;
    reg [1:0]  md;

    // ---------------- 时序与行请求 ----------------
    // 行 L 是否为视频行，以及其源行号
    function in_view(input [1:0] m, input [15:0] v);
        in_view = (m == 0) ? (v >= VY0 && v < VY0 + VH) : (v >= FY0 && v < FY0 + FH);
    endfunction
    wire [15:0] v2 = (vc + 2 >= V_TOT) ? vc + 2 - V_TOT : vc + 2;
    wire [15:0] src_line = (md == 0) ? v2 - VY0 : ((v2 - FY0) * 2) / 3;
    always @(posedge clk) begin
        if (rst) begin
            hc <= 0; vc <= 0; md <= 0; req_valid <= 0; frame_pulse <= 0;
        end else begin
            req_valid <= 1'b0;
            frame_pulse <= 1'b0;
            if (hc == H_TOT - 1) begin
                hc <= 0;
                vc <= (vc == V_TOT - 1) ? 0 : vc + 1;
            end else
                hc <= hc + 1;
            if (hc == 0) begin
                if (vc == V_ACT) begin
                    req_data  <= {1'b1, 11'd0};
                    req_valid <= 1'b1;
                    md <= mode;
                    frame_pulse <= 1'b1;
                end else if (in_view(md, v2)) begin
                    req_data  <= {1'b0, src_line[10:0]};
                    req_valid <= 1'b1;
                end
            end
        end
    end

    // ---------------- 第 0 级：取视频像素、发 OSD 地址 ----------------
    wire act = (hc < H_ACT) && (vc < V_ACT);
    wire drain = (vc >= V_ACT) && (vc < V_ACT + V_FP);
    wire vid_row = in_view(md, vc);
    wire [15:0] fx = hc - FX0;
    wire vid_col = (md == 0) ? (hc < 2 * VW) : (hc >= FX0 && hc < FX0 + FW);
    wire vid = act && vid_row && vid_col;
    // 1.5 倍：每 3 个输出像素弹出 2 个（相位 0、2 弹出，相位 1 重复）
    reg [1:0] ph3;
    wire pop_ph = (md == 0) || (ph3 != 1);
    always @(*) f_ready = (vid && pop_ph) || drain;

    reg  [23:0] hold;
    wire [23:0] vpx = (md != 0 && ph3 == 1) ? hold : (f_valid ? f_data : 24'h000000);
    always @(posedge clk) begin
        if (rst) begin
            ph3 <= 0; underflow <= 0;
        end else begin
            if (vid) ph3 <= (ph3 == 2) ? 0 : ph3 + 1;
            else ph3 <= 0;
            if (vid && pop_ph && f_valid) hold <= f_data;
            if (vid && pop_ph && !f_valid) underflow <= underflow + 1'b1;
        end
    end

    // OSD 地址
    wire [15:0] crow = vc / CH, ccol = hc / CW;
    wire [10:0] taddr = crow * COLS + ccol;
    wire [7:0]  tcode;
    dcram #(.W(8), .D(2048), .AW(11)) u_txt (
        .wclk(osd_clk), .we(osd_we), .waddr(osd_addr), .wdata(osd_data),
        .rclk(clk), .raddr(taddr), .rdata(tcode)
    );

    // 流水寄存
    reg [23:0] p1, p2, p3;
    reg        a1, a2, a3, v1, v2r, v3;
    reg        hs1, hs2, hs3, vs1, vs2, vs3;
    reg [3:0]  fr1, fr2;       // 字形行
    reg [2:0]  fb1, fb2, fb3;  // 字形列
    wire hsync = (hc >= H_ACT + H_FP) && (hc < H_ACT + H_FP + H_SYNC);
    wire vsync = (vc >= V_ACT + V_FP) && (vc < V_ACT + V_FP + V_SYNC);
    always @(posedge clk) begin
        p1 <= vpx; a1 <= act; v1 <= vid; hs1 <= hsync; vs1 <= vsync;
        fr1 <= (vc % CH) / SC; fb1 <= (hc % CW) / SC;
        p2 <= p1; a2 <= a1; v2r <= v1; hs2 <= hs1; vs2 <= vs1; fr2 <= fr1; fb2 <= fb1;
        p3 <= p2; a3 <= a2; v3 <= v2r; hs3 <= hs2; vs3 <= vs2; fb3 <= fb2;
    end

    // 第 1 级：字符码 → 字库地址；第 2 级：字形字节
    reg  [7:0]  code2, code3;
    wire [7:0]  fbyte;
    wire [6:0]  cidx = (tcode[6:0] >= 32) ? tcode[6:0] - 7'd32 : 7'd0;
    reg  [10:0] faddr;
    always @(posedge clk) begin
        faddr <= cidx * 16 + fr1;
        code2 <= tcode;
        code3 <= code2;
    end
    sdpram #(.W(8), .D(1536), .AW(11), .INIT(FONT)) u_font (
        .clk(clk), .we(1'b0), .waddr(11'd0), .wdata(8'd0),
        .re(1'b1), .raddr(faddr), .rdata(fbyte)
    );

    // 第 3 级：合成输出
    wire        fbit = fbyte[7 - fb3];
    wire [23:0] bg   = v3 ? p3 : 24'h202020;
    wire [23:0] dim  = {2'b0, bg[23:18], 2'b0, bg[15:10], 2'b0, bg[7:2]};
    wire [23:0] fg   = code3[7] ? 24'h00E0FF : 24'hFFFFFF;   // {B,G,R}
    wire [23:0] px   = (code3 == 0) ? bg : (fbit ? fg : dim);
    always @(posedge clk) begin
        o_hs <= hs3;
        o_vs <= vs3;
        o_de <= a3;
        {o_b, o_g, o_r} <= a3 ? px : 24'h0;
    end
endmodule
