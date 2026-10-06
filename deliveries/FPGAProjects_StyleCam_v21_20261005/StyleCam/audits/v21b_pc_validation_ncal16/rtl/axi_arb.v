// AXI4 仲裁器：NR 个读主机、NW 个写主机 → 1 个从机（DDR 控制器 AXI 口）
// 以突发为单位轮询；读数据按 AR 授权顺序回送，写数据/响应按 AW 授权顺序路由
// 前提：从机对同一 ID 保序（本设计所有主机 ID 均为 0）
module axi_arb #(
    parameter NR = 2,
    parameter NW = 2,
    parameter DW = 128,
    parameter AW = 32
)(
    input                   clk,
    input                   rst,
    // 读主机（扁平化总线）
    input  [NR*AW-1:0]      m_araddr,
    input  [NR*8-1:0]       m_arlen,
    input  [NR-1:0]         m_arvalid,
    output reg [NR-1:0]     m_arready,
    output [DW-1:0]         m_rdata,
    output                  m_rlast,
    output [1:0]            m_rresp,
    output reg [NR-1:0]     m_rvalid,
    input  [NR-1:0]         m_rready,
    // 写主机
    input  [NW*AW-1:0]      m_awaddr,
    input  [NW*8-1:0]       m_awlen,
    input  [NW-1:0]         m_awvalid,
    output reg [NW-1:0]     m_awready,
    input  [NW*DW-1:0]      m_wdata,
    input  [NW*DW/8-1:0]    m_wstrb,
    input  [NW-1:0]         m_wlast,
    input  [NW-1:0]         m_wvalid,
    output reg [NW-1:0]     m_wready,
    output reg [NW-1:0]     m_bvalid,
    input  [NW-1:0]         m_bready,
    // 从机
    output reg [AW-1:0]     s_araddr,
    output reg [7:0]        s_arlen,
    output reg              s_arvalid,
    input                   s_arready,
    input  [DW-1:0]         s_rdata,
    input                   s_rlast,
    input  [1:0]            s_rresp,
    input                   s_rvalid,
    output reg              s_rready,
    output reg [AW-1:0]     s_awaddr,
    output reg [7:0]        s_awlen,
    output reg              s_awvalid,
    input                   s_awready,
    output reg [DW-1:0]     s_wdata,
    output reg [DW/8-1:0]   s_wstrb,
    output reg              s_wlast,
    output reg              s_wvalid,
    input                   s_wready,
    input                   s_bvalid,
    output reg              s_bready
);
    localparam QA = 3;
    integer i;

    // ---------------- 读 ----------------
    reg [7:0]  rq [0:(1<<QA)-1];
    reg [QA:0] rq_w, rq_r;
    wire       rq_full  = (rq_w - rq_r) == (1 << QA);
    wire       rq_empty = (rq_w == rq_r);
    reg [7:0]  ar_rr, ar_pick;
    reg        ar_any;
    always @(*) begin
        ar_any = 1'b0;
        ar_pick = 0;
        for (i = NR - 1; i >= 0; i = i - 1)
            if (m_arvalid[(ar_rr + 1 + i) % NR]) begin
                ar_any = 1'b1;
                ar_pick = (ar_rr + 1 + i) % NR;
            end
    end
    reg [7:0] ar_sel;
    always @(posedge clk) begin
        if (rst) begin
            s_arvalid <= 1'b0; rq_w <= 0; ar_rr <= NR - 1;
        end else begin
            if (s_arvalid && s_arready) begin
                s_arvalid <= 1'b0;
                rq[rq_w[QA-1:0]] <= ar_sel;
                rq_w <= rq_w + 1'b1;
            end else if (!s_arvalid && ar_any && !rq_full) begin
                s_arvalid <= 1'b1;
                s_araddr  <= m_araddr[ar_pick*AW +: AW];
                s_arlen   <= m_arlen[ar_pick*8 +: 8];
                ar_sel    <= ar_pick;
                ar_rr     <= ar_pick;
            end
        end
    end
    always @(*) begin
        m_arready = 0;
        if (s_arvalid && s_arready) m_arready[ar_sel] = 1'b1;
    end
    // 注意：主机的 arvalid 在 m_arready 到来前保持，授权后本拍即握手
    wire [7:0] rsel = rq[rq_r[QA-1:0]];
    assign m_rdata = s_rdata;
    assign m_rlast = s_rlast;
    assign m_rresp = s_rresp;
    always @(*) begin
        m_rvalid = 0;
        s_rready = 1'b0;
        if (!rq_empty) begin
            m_rvalid[rsel] = s_rvalid;
            s_rready = m_rready[rsel];
        end
    end
    always @(posedge clk) begin
        if (rst) rq_r <= 0;
        else if (!rq_empty && s_rvalid && s_rready && s_rlast) rq_r <= rq_r + 1'b1;
    end

    // ---------------- 写 ----------------
    reg [7:0]  wq [0:(1<<QA)-1];
    reg [QA:0] wq_w, wq_r;
    reg [7:0]  bq [0:(1<<QA)-1];
    reg [QA:0] bq_w, bq_r;
    wire       wq_full  = (wq_w - wq_r) == (1 << QA) || (bq_w - bq_r) == (1 << QA);
    wire       wq_empty = (wq_w == wq_r);
    wire       bq_empty = (bq_w == bq_r);
    reg [7:0]  aw_rr, aw_pick, aw_sel;
    reg        aw_any;
    always @(*) begin
        aw_any = 1'b0;
        aw_pick = 0;
        for (i = NW - 1; i >= 0; i = i - 1)
            if (m_awvalid[(aw_rr + 1 + i) % NW]) begin
                aw_any = 1'b1;
                aw_pick = (aw_rr + 1 + i) % NW;
            end
    end
    always @(posedge clk) begin
        if (rst) begin
            s_awvalid <= 1'b0; wq_w <= 0; aw_rr <= NW - 1;
        end else begin
            if (s_awvalid && s_awready) begin
                s_awvalid <= 1'b0;
                wq[wq_w[QA-1:0]] <= aw_sel;
                wq_w <= wq_w + 1'b1;
            end else if (!s_awvalid && aw_any && !wq_full) begin
                s_awvalid <= 1'b1;
                s_awaddr  <= m_awaddr[aw_pick*AW +: AW];
                s_awlen   <= m_awlen[aw_pick*8 +: 8];
                aw_sel    <= aw_pick;
                aw_rr     <= aw_pick;
            end
        end
    end
    always @(*) begin
        m_awready = 0;
        if (s_awvalid && s_awready) m_awready[aw_sel] = 1'b1;
    end
    wire [7:0] wsel = wq[wq_r[QA-1:0]];
    always @(*) begin
        m_wready = 0;
        s_wvalid = 1'b0;
        s_wdata  = m_wdata[wsel*DW +: DW];
        s_wstrb  = m_wstrb[wsel*DW/8 +: DW/8];
        s_wlast  = m_wlast[wsel];
        if (!wq_empty) begin
            s_wvalid = m_wvalid[wsel];
            m_wready[wsel] = s_wready;
        end
    end
    wire [7:0] bsel = bq[bq_r[QA-1:0]];
    always @(*) begin
        m_bvalid = 0;
        s_bready = 1'b0;
        if (!bq_empty) begin
            m_bvalid[bsel] = s_bvalid;
            s_bready = m_bready[bsel];
        end
    end
    always @(posedge clk) begin
        if (rst) begin
            wq_r <= 0; bq_w <= 0; bq_r <= 0;
        end else begin
            if (!wq_empty && s_wvalid && s_wready && s_wlast) begin
                bq[bq_w[QA-1:0]] <= wsel;
                bq_w <= bq_w + 1'b1;
                wq_r <= wq_r + 1'b1;
            end
            if (!bq_empty && s_bvalid && s_bready) bq_r <= bq_r + 1'b1;
        end
    end
endmodule
