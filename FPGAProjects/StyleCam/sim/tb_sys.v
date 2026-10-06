`timescale 1ns/1ps
// 整链路仿真：摄像头 → 降采样 → DDR → NN → DDR → 显示合成（含 OSD），APB 模拟 CPU
module tb_sys;
    parameter IW = 112, IH = 72, XOFF = 8, CW = 96;
    parameter NW = 32, NH = 24, BL = 8;
    parameter H_ACT = 80, H_FP = 4, H_SYNC = 4, H_BP = 8;
    parameter V_ACT = 40, V_FP = 2, V_SYNC = 2, V_BP = 4;
    parameter VY0 = 8, SC = 1, NN_ASYNC = 1;
    localparam DW = 128, AW = 32;
    localparam NCW = IW / 2 * IH;

    reg clk_cam = 0, clk_axi = 0, clk_pix = 0, clk_nn = 0;
    always #3.5 clk_nn = ~clk_nn;
    always #6.5 clk_cam = ~clk_cam;
    always #5   clk_axi = ~clk_axi;
    always #12.5 clk_pix = ~clk_pix;
    reg rst = 1;

    // ---------------- 摄像头源 ----------------
    reg [47:0] cmem [0:NCW-1];
    initial $readmemh("cam.hex", cmem);
    reg        cv = 0, csof = 0;
    reg [47:0] cd = 0;
    integer cx = 0, cy = 0, cblank = 0;
    always @(posedge clk_cam) if (!rst) begin
        cv <= 0; csof <= 0;
        if (cblank > 0) cblank <= cblank - 1;
        else begin
            cv <= 1; cd <= cmem[cy * (IW / 2) + cx]; csof <= (cx == 0 && cy == 0);
            if (cx == IW / 2 - 1) begin
                cx <= 0; cblank <= 6;
                if (cy == IH - 1) begin cy <= 0; cblank <= 200; end
                else cy <= cy + 1;
            end else cx <= cx + 1;
        end
    end

    // ---------------- APB CPU 模型 ----------------
    reg  [11:0] paddr = 0;
    reg         psel = 0, penable = 0, pwrite = 0;
    reg  [31:0] pwdata = 0;
    wire [31:0] prdata;
    wire        irq;
    task apb_w(input [11:0] a, input [31:0] d);
        begin
            @(posedge clk_axi); paddr <= a; pwdata <= d; pwrite <= 1; psel <= 1; penable <= 0;
            @(posedge clk_axi); penable <= 1;
            @(posedge clk_axi); psel <= 0; penable <= 0; pwrite <= 0;
            repeat (4) @(posedge clk_axi);
        end
    endtask
    task apb_r(input [11:0] a, output [31:0] d);
        begin
            @(posedge clk_axi); paddr <= a; pwrite <= 0; psel <= 1; penable <= 0;
            @(posedge clk_axi); penable <= 1;
            @(posedge clk_axi); d = prdata; psel <= 0; penable <= 0;
        end
    endtask

    // ---------------- DUT ----------------
    wire [AW-1:0] araddr, awaddr;
    wire [7:0] arlen, awlen;
    wire arvalid, arready, rlast, rvalid, rready, awvalid, awready, wlast, wvalid, wready, bvalid, bready;
    wire [DW-1:0] rdata, wdata;
    wire [DW/8-1:0] wstrb;
    wire hs, vs, de;
    wire [7:0] vr, vg, vb;
    vision_top #(.CAM_RAW(0), .IW(IW), .IH(IH), .XOFF(XOFF), .CW(CW), .NW(NW), .NH(NH), .STRIDE(32'h1000), .BL(BL), .MBS(8), .NN_ASYNC(NN_ASYNC),
                 .H_ACT(H_ACT), .H_FP(H_FP), .H_SYNC(H_SYNC), .H_BP(H_BP),
                 .V_ACT(V_ACT), .V_FP(V_FP), .V_SYNC(V_SYNC), .V_BP(V_BP), .VY0(VY0), .SC(SC),
                 .FONT("font8x16.mem")) dut (
        .clk_cam(clk_cam), .clk_axi(clk_axi), .clk_pix(clk_pix), .clk_nn(clk_nn),
        .rst_cam(rst), .rst_axi(rst), .rst_pix(rst),
        .cam_valid(cv), .cam_sof(csof), .cam_data(cd), .raw_vs(1'b0), .cam_raw(40'd0),
        .paddr(paddr), .psel(psel), .penable(penable), .pwrite(pwrite), .pwdata(pwdata),
        .prdata(prdata), .pready(), .pslverr(), .irq(irq),
        .m_araddr(araddr), .m_arlen(arlen), .m_arsize(), .m_arburst(), .m_arvalid(arvalid), .m_arready(arready),
        .m_rdata(rdata), .m_rlast(rlast), .m_rvalid(rvalid), .m_rready(rready),
        .m_awaddr(awaddr), .m_awlen(awlen), .m_awsize(), .m_awburst(), .m_awvalid(awvalid), .m_awready(awready),
        .m_wdata(wdata), .m_wstrb(wstrb), .m_wlast(wlast), .m_wvalid(wvalid), .m_wready(wready),
        .m_bvalid(bvalid), .m_bready(bready),
        .vid_hs(hs), .vid_vs(vs), .vid_de(de), .vid_r(vr), .vid_g(vg), .vid_b(vb));
    axi_mem #(.DW(DW), .MEMSZ(1 << 16)) u_mem (
        .clk(clk_axi), .rst(rst),
        .araddr(araddr), .arlen(arlen), .arvalid(arvalid), .arready(arready),
        .rdata(rdata), .rlast(rlast), .rresp(), .rvalid(rvalid), .rready(rready),
        .awaddr(awaddr), .awlen(awlen), .awvalid(awvalid), .awready(awready),
        .wdata(wdata), .wstrb(wstrb), .wlast(wlast), .wvalid(wvalid), .wready(wready),
        .bvalid(bvalid), .bready(bready));

    // ---------------- 显示抓帧 ----------------
    reg        cap = 0;
    reg [1:0]  cap_state = 0;
    integer    fcap, npx = 0, vs_cnt = 0;
    reg        vs_d = 0;
    reg [255:0] cap_name;
    always @(posedge clk_pix) begin
        vs_d <= vs;
        if (vs && !vs_d) begin
            vs_cnt <= vs_cnt + 1;
            if (cap_state == 1) begin cap_state <= 2; npx = 0; end
            else if (cap_state == 2) begin cap_state <= 3; $fclose(fcap); end
        end
        if (cap_state == 2 && de) begin
            $fwrite(fcap, "%02x%02x%02x\n", vb, vg, vr);
            npx = npx + 1;
        end
    end
    task capture(input [255:0] name);
        begin
            fcap = $fopen(name, "w");
            cap_state = 1;
            wait (cap_state == 3);
            $display("抓帧 %0s 像素 %0d", name, npx);
            cap_state = 0;
        end
    endtask

    integer cyc = 0;
    always @(posedge clk_axi) begin
        cyc <= cyc + 1;
        if (cyc > 3000000) begin $display("TIMEOUT"); $finish; end
    end

    reg [31:0] r, s1lo, s1hi, s2lo, s2hi;
    integer fst, k;
    initial begin
        repeat (10) @(posedge clk_axi);
        rst = 0;
        apb_r(12'h000, r); $display("ID = %h", r);
        // OSD：第 0 行第 8、9 列写 "OK"（第 9 列黄色），位于视频区外
        apb_w(12'h808, 32'h0000_0000 | 8'h4F | ((8'h4B | 8'h80) << 8));
        apb_w(12'h008, 32'd0);                // 风格 0
        apb_w(12'h034, 32'd3);                // 中断使能
        apb_w(12'h040, 32'd1);                // IN 统计：预备第 1 层，下一 NN 帧开始累加
        apb_w(12'h004, 32'h1);                // nn_en=1，模式 0（并排）
        // 等 NN 完成 2 帧（第 2 帧起显示一定是最新风格图）
        r = 0;
        while (r < 2) begin repeat (200) @(posedge clk_axi); apb_r(12'h014, r); end
        $display("NN 帧 %0d，摄像头帧 %0d，时间 %0t", r, 0, $time);
        apb_r(12'h018, r); $display("NN 单帧周期 %0d", r);
        // 读出统计量（第 1 层各通道 Σa 低 32 位、Σa² 低 32 位）
        apb_r(12'h040, r); $display("STAT_CTRL %0d", r);
        fst = $fopen("stats_sys.txt", "w");
        for (k = 0; k < 24; k = k + 1) begin
            apb_w(12'h044, k);
            apb_r(12'h048, s1lo); apb_r(12'h04C, s1hi); apb_r(12'h050, s2lo); apb_r(12'h054, s2hi);
            $fwrite(fst, "%0d %0d %0d %0d\n", s1lo, s1hi, s2lo, s2hi);
        end
        $fclose(fst);
        repeat (2) @(posedge vs);
        capture("disp_m0.txt");
        apb_w(12'h004, 32'h5);                // 模式 1：风格图 1.5 倍全屏
        repeat (3) @(posedge vs);
        capture("disp_m1.txt");
        apb_r(12'h03C, r); $display("显示欠载 %0d", r);
        apb_r(12'h030, r); $display("IRQ_STATUS %0d irq=%0d", r, irq);
        apb_r(12'h010, r); $display("摄像头帧 %0d", r);
        apb_r(12'h068, r); $display("运动检测帧 %0d", r);
        apb_r(12'h05C, r); $display("运动块数 %0d（静止画面应为 0）", r);
        begin : camstat
            reg [31:0] sr, sg, sb, nh, sq;
            apb_r(12'h080, sr); apb_r(12'h084, sg); apb_r(12'h088, sb); apb_r(12'h08C, nh); apb_r(12'h090, sq);
            $display("CAMSTAT %0d %0d %0d %0d %0d", sr, sg, sb, nh, sq);
        end
        $finish;
    end
`include "frame_id_monitor.vh"
endmodule
