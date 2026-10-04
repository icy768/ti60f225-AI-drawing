`timescale 1ns/1ps
// 仿真用 AXI4 从机存储器：INCR 突发，随机握手延迟，读请求队列保序
module axi_mem #(
    parameter DW    = 128,
    parameter AW    = 32,
    parameter MEMSZ = 1 << 22,
    parameter SEED  = 7,
    parameter RND   = 1        // 1：随机插入等待
)(
    input               clk,
    input               rst,
    input  [AW-1:0]     araddr,
    input  [7:0]        arlen,
    input               arvalid,
    output reg          arready,
    output reg [DW-1:0] rdata,
    output reg          rlast,
    output [1:0]        rresp,
    output reg          rvalid,
    input               rready,
    input  [AW-1:0]     awaddr,
    input  [7:0]        awlen,
    input               awvalid,
    output reg          awready,
    input  [DW-1:0]     wdata,
    input  [DW/8-1:0]   wstrb,
    input               wlast,
    input               wvalid,
    output reg          wready,
    output reg          bvalid,
    input               bready
);
    localparam NB = DW / 8;
    reg [7:0] mem [0:MEMSZ-1];
    integer seed = SEED, k;
    assign rresp = 2'b00;

    function rnd_ok;
        input integer dummy;
        rnd_ok = RND ? (($random(seed) & 3) != 0) : 1'b1;
    endfunction

    // 读：请求队列
    reg [AW-1:0] qa [0:15];
    reg [7:0]    ql [0:15];
    reg [4:0]    qw, qr;
    reg [AW-1:0] ra;
    reg [8:0]    rleft;
    reg          ract;
    always @(posedge clk) begin
        if (rst) begin
            arready <= 0; rvalid <= 0; qw <= 0; qr <= 0; ract <= 0;
        end else begin
            arready <= ((qw - qr) < 12) && rnd_ok(0);
            if (arvalid && arready) begin
                qa[qw[3:0]] <= araddr;
                ql[qw[3:0]] <= arlen;
                qw <= qw + 1;
            end
            if (rvalid && rready) begin
                rvalid <= 0;
                if (rlast) ract <= 0;
            end
            if (!ract && qw != qr && !(rvalid && !rready)) begin
                ra <= qa[qr[3:0]];
                rleft <= ql[qr[3:0]] + 1;
                qr <= qr + 1;
                ract <= 1;
            end else if (ract && (!rvalid || rready) && rleft != 0 && rnd_ok(0)) begin
                for (k = 0; k < NB; k = k + 1) rdata[k*8 +: 8] <= mem[(ra + k) % MEMSZ];
                rlast  <= (rleft == 1);
                rvalid <= 1;
                ra     <= ra + NB;
                rleft  <= rleft - 1;
            end
        end
    end

    // 写：一次一个突发
    reg [AW-1:0] wa;
    reg          wact, bpend;
    always @(posedge clk) begin
        if (rst) begin
            awready <= 0; wready <= 0; bvalid <= 0; wact <= 0; bpend <= 0;
        end else begin
            awready <= !wact && !bpend && !awready && rnd_ok(0);
            if (awvalid && awready) begin
                wa <= awaddr;
                wact <= 1;
                awready <= 0;
            end
            wready <= wact && rnd_ok(0);
            if (wvalid && wready && wact) begin
                for (k = 0; k < NB; k = k + 1)
                    if (wstrb[k]) mem[(wa + k) % MEMSZ] <= wdata[k*8 +: 8];
                wa <= wa + NB;
                if (wlast) begin
                    wact <= 0;
                    wready <= 0;
                    bpend <= 1;
                end
            end
            if (bpend && !bvalid && rnd_ok(0)) bvalid <= 1;
            if (bvalid && bready) begin
                bvalid <= 0;
                bpend <= 0;
            end
        end
    end
endmodule
