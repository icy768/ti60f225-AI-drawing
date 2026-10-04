// 通用小模块

// 同步 FIFO（首字直通），小深度：移位链实现（写时整体移位、按占用数读最老元素），映射 SRL8，
// 比寄存器数组 + 读选择器省（深度 4 时每位 1 个 SRL8）；也不会被综合器塞进整块 M10K
module sfifo #(
    parameter W  = 8,
    parameter AW = 2
)(
    input              clk,
    input              rst,
    input  [W-1:0]     i_data,
    input              i_valid,
    output             i_ready,
    output [W-1:0]     o_data,
    output             o_valid,
    input              o_ready,
    output [AW:0]      count
);
    localparam D = 1 << AW;
    reg [W-1:0] sr [0:D-1];
    reg [AW:0]  cnt;
    wire        we = i_valid && i_ready;
    wire        re = o_valid && o_ready;
    wire [AW:0] ra = cnt - 1'b1;
    integer k;
    assign count   = cnt;
    assign i_ready = (cnt != D);
    assign o_valid = (cnt != 0);
    assign o_data  = sr[ra[AW-1:0]];
    always @(posedge clk)
        if (we) begin
            sr[0] <= i_data;
            for (k = 1; k < D; k = k + 1) sr[k] <= sr[k-1];
        end
    always @(posedge clk)
        if (rst) cnt <= 0;
        else     cnt <= cnt + we - re;
endmodule

// 移位寄存器 FIFO：写时整体移位（sr[0] 最新），按占用数寻址读出最老元素；无复位的移位链可映射 XLR 的 SRL8
// （8 深、支持动态读地址，级联），小深度宽数据时远比触发器数组 + 大选择器省
module srlfifo #(
    parameter W = 8,
    parameter D = 16
)(
    input              clk,
    input              rst,
    input  [W-1:0]     din,
    input              we,          // 满时须同拍 re 才能写
    input              re,          // 空时不得读
    output [W-1:0]     dout,        // 最老元素（空时无意义）
    output             empty,
    output             full
);
    localparam AW = (D > 1) ? $clog2(D) : 1;
    reg [W-1:0] sr [0:D-1];
    reg [AW:0]  cnt;
    integer k;
    always @(posedge clk)
        if (we) begin
            sr[0] <= din;
            for (k = 1; k < D; k = k + 1) sr[k] <= sr[k-1];
        end
    wire [AW:0] ra = cnt - 1'b1;
    assign dout  = sr[ra[AW-1:0]];
    assign empty = (cnt == 0);
    assign full  = (cnt == D);
    always @(posedge clk)
        if (rst) cnt <= 0;
        else     cnt <= cnt + we - re;
endmodule

// 权重 RAM：按 32 位分道写（CPU 逐字装载），整行同步读
// 前 NL-1 道先存暂存寄存器，写到最后一道时整行写入：存储体只有一个全宽写口，综合器能按 20 位宽排满 M10K
// （分道写口会让每道 32 位各占 2 块，如 384 位宽要 24 块，整行写只要 20 块）。
// 装载顺序要求：每个地址内按道号 0..NL-1 依次写（gen_rtl/export_blob 生成的装载脚本即如此）
module wram #(
    parameter W    = 96,
    parameter D    = 64,
    parameter AW   = 6,
    parameter INIT = ""
)(
    input               clk,
    input               we,
    input  [4:0]        wlane,
    input  [AW-1:0]     waddr,
    input  [31:0]       wdata,
    input               re,
    input  [AW-1:0]     raddr,
    output reg [W-1:0]  rdata
);
    // W 须为 32 的整数倍
    localparam NL = W / 32;
    reg [W-1:0] mem [0:D-1];
    initial if (INIT != "") $readmemh(INIT, mem);
    generate
        if (NL == 1) begin : g_one
            always @(posedge clk) if (we) mem[waddr] <= wdata;
        end else begin : g_stage
            reg [W-33:0] stage;
            always @(posedge clk)
                if (we) begin
                    if (wlane == NL - 1) mem[waddr] <= {wdata, stage};
                    else stage[wlane*32 +: 32] <= wdata;
                end
        end
    endgenerate
    always @(posedge clk)
        if (re) rdata <= mem[raddr];
endmodule

// 简单双口 RAM：同步写、同步读（映射 M10K）
// 深度 >2048 且不是 2 的幂时拆成 2048 + 余数两段：综合器会把整体深度向上取到 2 的幂
// （如 2560x32 占 16 块），分段后分别选最省的配置（2048x5 七块 + 512x20 两块 = 9 块）；读出时序不变
module sdpram #(
    parameter W    = 32,
    parameter D    = 1024,
    parameter AW   = 10,
    parameter INIT = ""
)(
    input               clk,
    input               we,
    input  [AW-1:0]     waddr,
    input  [W-1:0]      wdata,
    input               re,
    input  [AW-1:0]     raddr,
    output [W-1:0]      rdata
);
    localparam SPLIT = (D > 2048) && ((D & (D - 1)) != 0) && (INIT == "");
    generate
        if (SPLIT) begin : g_split
            localparam D1 = D - 2048;
            reg [W-1:0] m0 [0:2047];
            reg [W-1:0] m1 [0:D1-1];
            reg [W-1:0] q0, q1;
            reg         sel;
            wire        whi = (waddr >= 2048);
            wire        rhi = (raddr >= 2048);
            wire [AW-1:0] wa1 = waddr - 2048;
            wire [AW-1:0] ra1 = raddr - 2048;
            always @(posedge clk) begin
                if (we && !whi) m0[waddr[10:0]] <= wdata;
                if (we && whi)  m1[wa1] <= wdata;
                if (re) begin
                    q0  <= m0[raddr[10:0]];
                    q1  <= m1[ra1];
                    sel <= rhi;
                end
            end
            assign rdata = sel ? q1 : q0;
        end else begin : g_one
            reg [W-1:0] mem [0:D-1];
            reg [W-1:0] q;
            initial if (INIT != "") $readmemh(INIT, mem);
            always @(posedge clk) begin
                if (we) mem[waddr] <= wdata;
                if (re) q <= mem[raddr];
            end
            assign rdata = q;
        end
    endgenerate
endmodule

// IN 统计单元（分时复用：一次只统计一个层）
//   arm 后在下一个 frame_start 清零并开始累加，frame_end 时冻结（done=1），直到再次 arm
//   逐通道 Σa（40 位）与 Σa²（60 位）；CPU 按通道号读出（rd_idx 变化后 1 拍出数）
//   累加器放 M10K（读改写，读出后下一拍写回）：输入节拍来自 requant，相邻两拍至少隔 1 拍、且通道号不同，无读写冲突；
//   帧首不逐个清零，而是清"本帧已写过"标志 vld，未写过的通道按 0 参与累加 / 读出为 0
module in_stats #(
    parameter CMAX = 32
)(
    input               clk,
    input               rst,
    input               arm,
    input               frame_start,
    input               frame_end,
    input               i_v,
    input  [18:0]       i_a,
    input  [7:0]        i_ch,
    input  [7:0]        rd_idx,
    output [39:0]       rd_s1,
    output [59:0]       rd_s2,
    output reg          done,
    output reg          busy
);
    localparam CAW = (CMAX > 1) ? $clog2(CMAX) : 1;
    (* syn_ramstyle = "block_ram" *) reg [39:0] m1 [0:CMAX-1];
    (* syn_ramstyle = "block_ram" *) reg [59:0] m2 [0:CMAX-1];
    reg [CMAX-1:0]    vld;
    reg armed;
    // 输入先打一拍：统计抽头来自 requant 的组合输出，再经 stylenet_top 的层选择器，不打拍会与平方乘法器连成 NN 域关键路径
    reg               v0;
    reg [18:0]        a0r;
    reg [7:0]         c0;
    reg               v1, v2;
    reg signed [18:0] a1, a2;
    reg [7:0]         c1, c2;
    reg signed [37:0] sq1, sq2;
    reg [39:0]        q1;
    reg [59:0]        q2;
    reg               qv;

    // 读口：统计期间给读改写用，其余时间给 CPU 读出
    wire [CAW-1:0] ra = busy ? c1[CAW-1:0] : rd_idx[CAW-1:0];
    always @(posedge clk) begin
        q1 <= m1[ra];
        q2 <= m2[ra];
        qv <= vld[ra];
    end
    assign rd_s1 = qv ? q1 : 40'd0;
    assign rd_s2 = qv ? q2 : 60'd0;

    wire signed [39:0] o1 = qv ? $signed(q1) : 40'sd0;
    wire signed [59:0] o2 = qv ? $signed(q2) : 60'sd0;
    wire acc = v2 && !frame_start;      // 是否计入只看第 1 级采样时的 busy（与原寄存器版语义一致）
    always @(posedge clk) begin
        if (acc) begin
            m1[c2[CAW-1:0]] <= o1 + a2;
            m2[c2[CAW-1:0]] <= o2 + sq2;
        end
    end

    always @(posedge clk) begin
        if (rst) begin
            armed <= 0; busy <= 0; done <= 0; v0 <= 0; v1 <= 0; v2 <= 0; vld <= 0;
        end else begin
            if (arm) begin armed <= 1'b1; done <= 1'b0; end
            if (frame_start && (armed || arm)) begin
                armed <= 1'b0;
                busy  <= 1'b1;
                vld   <= 0;
            end else if (acc)
                vld[c2[CAW-1:0]] <= 1'b1;
            if (frame_end && busy) begin busy <= 1'b0; done <= 1'b1; end
            // 四级流水：输入打拍 → 平方 → 读出旧值 → 累加写回
            v0  <= i_v;
            a0r <= i_a;
            c0  <= i_ch;
            v1  <= v0 && busy;
            a1  <= a0r;
            c1  <= c0;
            sq1 <= $signed(a0r) * $signed(a0r);
            v2  <= v1 && busy && !frame_start;
            a2  <= a1;
            c2  <= c1;
            sq2 <= sq1;
        end
    end
endmodule

// 单拍脉冲跨时钟域（翻转 + 三级同步 + 边沿检测）；两次脉冲间隔须大于目标域 3 拍
module pulse_sync (
    input   sclk,
    input   srst,
    input   spulse,
    input   dclk,
    input   drst,
    output  dpulse
);
    reg t;
    (* async_reg = "true" *) reg [2:0] s;
    always @(posedge sclk) if (srst) t <= 1'b0; else if (spulse) t <= ~t;
    always @(posedge dclk) if (drst) s <= 3'b0; else s <= {s[1:0], t};
    assign dpulse = s[2] ^ s[1];
endmodule

// 单比特电平两级同步
module bit_sync (
    input   dclk,
    input   d,
    output  q
);
    (* async_reg = "true" *) reg [1:0] s;
    always @(posedge dclk) s <= {s[0], d};
    assign q = s[1];
endmodule
