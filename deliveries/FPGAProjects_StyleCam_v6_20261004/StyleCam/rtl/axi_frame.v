// 跨时钟域 FIFO 与 AXI4 帧读写主机
// 帧格式：每像素 32 位 {8'h0, B, G, R}（R 在低字节），行优先连续存放，基址 4KB 对齐

// ---------------------------------------------------------------------------
// 异步 FIFO（格雷码指针，首字直通输出），存储体映射 M10K
// ---------------------------------------------------------------------------
module afifo #(
    parameter W  = 24,
    parameter AW = 9
)(
    input               wclk,
    input               wrst,
    input  [W-1:0]      wdata,
    input               wvalid,
    output              wready,
    output reg [AW:0]   wcount,
    input               rclk,
    input               rrst,
    output reg [W-1:0]  rdata,
    output reg          rvalid,
    input               rready
);
    // 深度 ≤16 时放寄存器（整块 M10K 装 16 个字太浪费），否则映射 M10K
    localparam RSTYLE = (AW <= 4) ? "registers" : "block_ram";
    (* syn_ramstyle = RSTYLE *) reg [W-1:0] mem [0:(1<<AW)-1];
    reg [AW:0] wbin, wgray, rbin, rgray;
    (* async_reg = "true" *) reg [AW:0] rg_w1, rg_w2;
    (* async_reg = "true" *) reg [AW:0] wg_r1, wg_r2;

    function [AW:0] b2g(input [AW:0] b);
        b2g = b ^ (b >> 1);
    endfunction
    function [AW:0] g2b(input [AW:0] g);
        integer i;
        begin
            g2b[AW] = g[AW];
            for (i = AW - 1; i >= 0; i = i - 1) g2b[i] = g2b[i+1] ^ g[i];
        end
    endfunction

    // 写侧
    wire [AW:0] wbin_n = wbin + 1'b1;
    wire full = (wgray == {~rg_w2[AW:AW-1], rg_w2[AW-2:0]});
    assign wready = !full;
    always @(posedge wclk) begin
        if (wrst) begin
            wbin <= 0; wgray <= 0; rg_w1 <= 0; rg_w2 <= 0; wcount <= 0;
        end else begin
            rg_w1 <= rgray;
            rg_w2 <= rg_w1;
            if (wvalid && !full) begin
                mem[wbin[AW-1:0]] <= wdata;
                wbin  <= wbin_n;
                wgray <= b2g(wbin_n);
            end
            wcount <= wbin - g2b(rg_w2);
        end
    end

    // 读侧：输出寄存器空或被取走时从存储体预取
    wire empty = (rgray == wg_r2);
    wire load  = !empty && (!rvalid || rready);
    wire [AW:0] rbin_n = rbin + 1'b1;
    always @(posedge rclk) begin
        if (rrst) begin
            rbin <= 0; rgray <= 0; wg_r1 <= 0; wg_r2 <= 0; rvalid <= 1'b0;
        end else begin
            wg_r1 <= wgray;
            wg_r2 <= wg_r1;
            if (load) begin
                rdata  <= mem[rbin[AW-1:0]];
                rvalid <= 1'b1;
                rbin   <= rbin_n;
                rgray  <= b2g(rbin_n);
            end else if (rready)
                rvalid <= 1'b0;
        end
    end
endmodule

// ---------------------------------------------------------------------------
// 同步 FIFO（BRAM 存储，首字直通），带占用计数
// ---------------------------------------------------------------------------
module bfifo #(
    parameter W  = 128,
    parameter AW = 5
)(
    input               clk,
    input               rst,
    input  [W-1:0]      wdata,
    input               wvalid,
    output              wready,
    output [W-1:0]      rdata,
    output              rvalid,
    input               rready,
    output reg [AW+1:0] count
);
    reg [W-1:0] mem [0:(1<<AW)-1];
    reg [AW:0]  wp, rp;
    reg [W-1:0] ob;
    reg         ov;
    wire [AW:0] used = wp - rp;
    assign wready = (used != (1 << AW));
    wire load = (used != 0) && (!ov || rready);
    assign rdata  = ob;
    assign rvalid = ov;
    always @(posedge clk) begin
        if (rst) begin
            wp <= 0; rp <= 0; ov <= 1'b0; count <= 0;
        end else begin
            if (wvalid && wready) begin
                mem[wp[AW-1:0]] <= wdata;
                wp <= wp + 1'b1;
            end
            if (load) begin
                ob <= mem[rp[AW-1:0]];
                ov <= 1'b1;
                rp <= rp + 1'b1;
            end else if (rready)
                ov <= 1'b0;
            count <= count + (wvalid && wready) - (rvalid && rready);
        end
    end
endmodule

// ---------------------------------------------------------------------------
// 帧写主机：24 位像素流 → 打包为 DW 位拍 → INCR 突发写（每突发 BL 拍）
// npix 需为 (DW/32)*BL 的整数倍
// ---------------------------------------------------------------------------
module axi_frame_wr #(
    parameter DW  = 128,
    parameter AW  = 32,
    parameter IDW = 4,
    parameter BL  = 16
)(
    input                 clk,
    input                 rst,
    input                 start,
    input  [AW-1:0]       base,
    input  [31:0]         npix,
    output reg            busy,
    output reg            done,
    input  [23:0]         s_data,
    input                 s_valid,
    output                s_ready,
    output [IDW-1:0]      awid,
    output reg [AW-1:0]   awaddr,
    output [7:0]          awlen,
    output [2:0]          awsize,
    output [1:0]          awburst,
    output reg            awvalid,
    input                 awready,
    output [DW-1:0]       wdata,
    output [DW/8-1:0]     wstrb,
    output                wlast,
    output                wvalid,
    input                 wready,
    input  [IDW-1:0]      bid,
    input  [1:0]          bresp,
    input                 bvalid,
    output                bready
);
    localparam PPB = DW / 32;
    localparam PW  = PPB * 24;  // FIFO 只存有效的 24 位像素：每 32 位的高字节恒为 0，出口处补回（128 位拍 7 块 → 96 位 5 块）
    localparam BBY = BL * DW / 8;
    assign awid    = 0;
    assign awlen   = BL - 1;
    assign awsize  = $clog2(DW / 8);
    assign awburst = 2'b01;
    assign wstrb   = {(DW/8){1'b1}};
    assign bready  = 1'b1;

    // 像素打包
    reg [PW-1:0] pk;
    reg [7:0]    pn;
    reg [31:0]   pin;          // 已接收像素
    wire         f_wready;
    wire [6:0]   f_cnt;
    wire         wvalid_i, wready_i;
    wire         pk_full = (pn == PPB);
    wire [PW-1:0] fdat;
    assign s_ready = busy && (pin != npix) && !pk_full;

    bfifo #(.W(PW), .AW(5)) u_f (
        .clk(clk), .rst(rst || start),
        .wdata(pk), .wvalid(pk_full), .wready(f_wready),
        .rdata(fdat), .rvalid(wvalid_i), .rready(wready_i), .count(f_cnt)
    );
    genvar gi;
    generate
        for (gi = 0; gi < PPB; gi = gi + 1) begin : g_ex
            assign wdata[gi*32 +: 32] = {8'h00, fdat[gi*24 +: 24]};
        end
    endgenerate

    // 突发控制
    reg [31:0] nburst, bursts_issued, bursts_done;
    reg [7:0]  wbeat;
    reg [15:0] w_pending;      // 已发地址、未发完数据的突发数（保证 AW 先于 W）
    wire       wact = (w_pending != 0);
    assign wvalid   = wact && wvalid_i;
    assign wready_i = wact && wready;
    assign wlast    = (wbeat == BL - 1);

    always @(posedge clk) begin
        if (rst) begin
            busy <= 1'b0; done <= 1'b0; awvalid <= 1'b0;
            pn <= 0; pin <= 0; w_pending <= 0; wbeat <= 0;
        end else begin
            done <= 1'b0;
            if (start) begin
                busy <= 1'b1;
                pn <= 0; pin <= 0;
                awaddr <= base;
                nburst <= npix / (PPB * BL);
                bursts_issued <= 0; bursts_done <= 0;
                w_pending <= 0; wbeat <= 0; awvalid <= 1'b0;
            end else if (busy) begin
                // 打包
                if (pk_full && f_wready) pn <= 0;
                if (s_valid && s_ready) begin
                    pk[pn*24 +: 24] <= s_data;
                    pn  <= pn + 1'b1;
                    pin <= pin + 1'b1;
                end
                // 地址：FIFO 已攒够一个突发的数据再发
                if (awvalid && awready) begin
                    awvalid <= 1'b0;
                    awaddr  <= awaddr + BBY;
                end
                if (!awvalid && bursts_issued != nburst &&
                    f_cnt >= BL * (w_pending + (awvalid ? 1 : 0) + 1)) begin
                    awvalid <= 1'b1;
                    bursts_issued <= bursts_issued + 1'b1;
                end
                // 数据
                if (wvalid && wready)
                    wbeat <= wlast ? 8'd0 : wbeat + 1'b1;
                w_pending <= w_pending + (awvalid && awready) - (wvalid && wready && wlast);
                // 响应
                if (bvalid) begin
                    bursts_done <= bursts_done + 1'b1;
                    if (bursts_done + 1 == nburst) begin
                        busy <= 1'b0;
                        done <= 1'b1;
                    end
                end
            end
        end
    end
endmodule

// ---------------------------------------------------------------------------
// 帧读主机：INCR 突发读 → 拆包为 24 位像素流；按 FIFO 余量发起突发（信用制）
// ---------------------------------------------------------------------------
module axi_frame_rd #(
    parameter DW  = 128,
    parameter AW  = 32,
    parameter IDW = 4,
    parameter BL  = 16
)(
    input                 clk,
    input                 rst,
    input                 start,
    input  [AW-1:0]       base,
    input  [31:0]         npix,
    output reg            busy,
    output reg            done,
    output [23:0]         m_data,
    output                m_valid,
    input                 m_ready,
    output [IDW-1:0]      arid,
    output reg [AW-1:0]   araddr,
    output [7:0]          arlen,
    output [2:0]          arsize,
    output [1:0]          arburst,
    output reg            arvalid,
    input                 arready,
    input  [IDW-1:0]      rid,
    input  [DW-1:0]       rdata,
    input  [1:0]          rresp,
    input                 rlast,
    input                 rvalid,
    output                rready
);
    localparam PPB = DW / 32;
    localparam PW  = PPB * 24;  // FIFO 只存每 32 位的低 24 位（高字节不用），128 位拍 7 块 → 96 位 5 块
    localparam BBY = BL * DW / 8;
    localparam FAW = 6;
    assign arid    = 0;
    assign arlen   = BL - 1;
    assign arsize  = $clog2(DW / 8);
    assign arburst = 2'b01;

    wire [PW-1:0] fd;
    wire [PW-1:0] rpk;
    wire          fv;
    reg           fr;
    wire [FAW+1:0] fcnt;
    wire          fwr;
    genvar gi;
    generate
        for (gi = 0; gi < PPB; gi = gi + 1) begin : g_pk
            assign rpk[gi*24 +: 24] = rdata[gi*32 +: 24];
        end
    endgenerate
    assign rready = 1'b1;       // 信用制保证 FIFO 不会溢出
    bfifo #(.W(PW), .AW(FAW)) u_f (
        .clk(clk), .rst(rst || start),
        .wdata(rpk), .wvalid(rvalid), .wready(fwr),
        .rdata(fd), .rvalid(fv), .rready(fr), .count(fcnt)
    );

    reg [31:0] nburst, issued, pout;
    reg [15:0] inflight;        // 已发地址、未收齐的拍数
    reg [7:0]  up;              // 当前拍内像素序号
    assign m_data  = fd[up*24 +: 24];
    assign m_valid = busy && fv;
    always @(*) fr = m_valid && m_ready && (up == PPB - 1);

    always @(posedge clk) begin
        if (rst) begin
            busy <= 1'b0; done <= 1'b0; arvalid <= 1'b0; inflight <= 0; up <= 0;
        end else begin
            done <= 1'b0;
            if (start) begin
                busy <= 1'b1;
                araddr <= base;
                nburst <= npix / (PPB * BL);
                issued <= 0; pout <= 0; inflight <= 0; up <= 0; arvalid <= 1'b0;
            end else if (busy) begin
                if (arvalid && arready) begin
                    arvalid <= 1'b0;
                    araddr  <= araddr + BBY;
                end
                if (!arvalid && issued != nburst &&
                    fcnt + inflight + BL <= (1 << FAW)) begin
                    arvalid <= 1'b1;
                    issued  <= issued + 1'b1;
                end
                inflight <= inflight + ((!arvalid && issued != nburst &&
                            fcnt + inflight + BL <= (1 << FAW)) ? BL : 0) - (rvalid ? 1 : 0);
                if (m_valid && m_ready) begin
                    up   <= (up == PPB - 1) ? 0 : up + 1'b1;
                    pout <= pout + 1'b1;
                    if (pout + 1 == npix) begin
                        busy <= 1'b0;
                        done <= 1'b1;
                    end
                end
            end
        end
    end
endmodule
