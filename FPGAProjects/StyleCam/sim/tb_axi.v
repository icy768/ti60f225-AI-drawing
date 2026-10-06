`timescale 1ns/1ps
// 帧读写主机 + 仲裁器 + 存储器模型：并发写两帧、并发读回校验
module tb_axi;
    parameter NPIX = 640 * 8;
    localparam DW = 128, AW = 32;
    reg clk = 0, rst = 1;
    always #5 clk = ~clk;
    integer seed = 3;

    function [23:0] pix(input integer fr, input integer i);
        pix = (i * 32'h9E3779B1 + fr * 32'h85EBCA6B) ^ (i >> 3);
    endfunction

    // 写主机
    reg  [1:0]  wstart;
    wire [1:0]  wbusy, wdone;
    reg  [31:0] wi [0:1];
    reg  [1:0]  sv;
    wire [1:0]  sr;
    wire [2*AW-1:0] awaddr;
    wire [15:0] awlen;
    wire [1:0]  awvalid, awready, wlast, wvalid, wready, bvalid, bready;
    wire [2*DW-1:0] wdata;
    wire [2*DW/8-1:0] wstrb;
    // 读主机
    reg  [1:0]  rstart;
    wire [1:0]  rbusy, rdone;
    wire [47:0] md;
    wire [1:0]  mv;
    reg  [1:0]  mr;
    reg  [31:0] ri [0:1];
    wire [2*AW-1:0] araddr;
    wire [15:0] arlen;
    wire [1:0]  arvalid, arready, rvalid, rready;
    wire [DW-1:0] rdata;
    wire rlast;

    genvar g;
    generate for (g = 0; g < 2; g = g + 1) begin : gm
        axi_frame_wr #(.DW(DW)) u_w (
            .clk(clk), .rst(rst), .start(wstart[g]), .base(32'h10000 + g * 32'h100000), .npix(NPIX),
            .busy(wbusy[g]), .done(wdone[g]),
            .s_data(pix(g, wi[g])), .s_valid(sv[g]), .s_ready(sr[g]),
            .awid(), .awaddr(awaddr[g*AW +: AW]), .awlen(awlen[g*8 +: 8]), .awsize(), .awburst(),
            .awvalid(awvalid[g]), .awready(awready[g]),
            .wdata(wdata[g*DW +: DW]), .wstrb(wstrb[g*DW/8 +: DW/8]), .wlast(wlast[g]),
            .wvalid(wvalid[g]), .wready(wready[g]),
            .bid(4'd0), .bresp(2'd0), .bvalid(bvalid[g]), .bready(bready[g]));
        axi_frame_rd #(.DW(DW)) u_r (
            .clk(clk), .rst(rst), .start(rstart[g]), .base(32'h10000 + g * 32'h100000), .npix(NPIX),
            .busy(rbusy[g]), .done(rdone[g]),
            .m_data(md[g*24 +: 24]), .m_valid(mv[g]), .m_ready(mr[g]),
            .arid(), .araddr(araddr[g*AW +: AW]), .arlen(arlen[g*8 +: 8]), .arsize(), .arburst(),
            .arvalid(arvalid[g]), .arready(arready[g]),
            .rid(4'd0), .rdata(rdata), .rresp(2'd0), .rlast(rlast), .rvalid(rvalid[g]), .rready(rready[g]));
    end endgenerate

    wire [AW-1:0] s_araddr, s_awaddr;
    wire [7:0] s_arlen, s_awlen;
    wire s_arvalid, s_arready, s_rlast, s_rvalid, s_rready, s_awvalid, s_awready;
    wire s_wlast, s_wvalid, s_wready, s_bvalid, s_bready;
    wire [DW-1:0] s_rdata, s_wdata;
    wire [DW/8-1:0] s_wstrb;
    axi_arb #(.NR(2), .NW(2), .DW(DW)) u_arb (
        .clk(clk), .rst(rst),
        .m_araddr(araddr), .m_arlen(arlen), .m_arvalid(arvalid), .m_arready(arready),
        .m_rdata(rdata), .m_rlast(rlast), .m_rresp(), .m_rvalid(rvalid), .m_rready(rready),
        .m_awaddr(awaddr), .m_awlen(awlen), .m_awvalid(awvalid), .m_awready(awready),
        .m_wdata(wdata), .m_wstrb(wstrb), .m_wlast(wlast), .m_wvalid(wvalid), .m_wready(wready),
        .m_bvalid(bvalid), .m_bready(bready),
        .s_araddr(s_araddr), .s_arlen(s_arlen), .s_arvalid(s_arvalid), .s_arready(s_arready),
        .s_rdata(s_rdata), .s_rlast(s_rlast), .s_rresp(2'd0), .s_rvalid(s_rvalid), .s_rready(s_rready),
        .s_awaddr(s_awaddr), .s_awlen(s_awlen), .s_awvalid(s_awvalid), .s_awready(s_awready),
        .s_wdata(s_wdata), .s_wstrb(s_wstrb), .s_wlast(s_wlast), .s_wvalid(s_wvalid), .s_wready(s_wready),
        .s_bvalid(s_bvalid), .s_bready(s_bready));
    axi_mem #(.DW(DW)) u_mem (
        .clk(clk), .rst(rst),
        .araddr(s_araddr), .arlen(s_arlen), .arvalid(s_arvalid), .arready(s_arready),
        .rdata(s_rdata), .rlast(s_rlast), .rresp(), .rvalid(s_rvalid), .rready(s_rready),
        .awaddr(s_awaddr), .awlen(s_awlen), .awvalid(s_awvalid), .awready(s_awready),
        .wdata(s_wdata), .wstrb(s_wstrb), .wlast(s_wlast), .wvalid(s_wvalid), .wready(s_wready),
        .bvalid(s_bvalid), .bready(s_bready));

    integer errs = 0, cyc = 0, k;
    initial begin
        wstart = 0; rstart = 0; sv = 0; mr = 0; wi[0] = 0; wi[1] = 0; ri[0] = 0; ri[1] = 0;
        repeat (4) @(posedge clk);
        rst <= 0;
        @(posedge clk); wstart <= 2'b11;
        @(posedge clk); wstart <= 0;
    end
    reg phase = 0;
    always @(posedge clk) if (!rst) begin
        cyc <= cyc + 1;
        for (k = 0; k < 2; k = k + 1) begin
            if (sv[k] && sr[k]) wi[k] <= wi[k] + 1;
            sv[k] <= wbusy[k] && (((sv[k] && sr[k]) ? wi[k] + 1 : wi[k]) < NPIX) && ($random(seed) & 1);
            if (mv[k] && mr[k]) begin
                if (md[k*24 +: 24] !== pix(k, ri[k])) begin
                    if (errs < 5) $display("ERR fr%0d px%0d got %h exp %h", k, ri[k], md[k*24 +: 24], pix(k, ri[k]));
                    errs = errs + 1;
                end
                ri[k] = ri[k] + 1;
            end
            mr[k] <= ($random(seed) % 3) != 0;
        end
        rstart <= 0;
        if (!phase && !wbusy[0] && !wbusy[1] && cyc > 10) begin
            phase <= 1;
            rstart <= 2'b11;
        end
        if (phase && !rbusy[0] && !rbusy[1] && !rstart && ri[0] == NPIX && ri[1] == NPIX) begin
            $display("AXI 帧读写：%0d 像素 x2，错误 %0d，周期 %0d -> %s", NPIX, errs, cyc, errs ? "FAIL" : "PASS");
            $finish;
        end
        if (cyc > 500000) begin
            $display("TIMEOUT wi=%0d/%0d ri=%0d/%0d", wi[0], wi[1], ri[0], ri[1]);
            $finish;
        end
    end
endmodule
