// 视觉子系统顶层：摄像头预处理（cam 域）+ 中枢（AXI 域）+ 显示（像素域），APB3 从机 + AXI4 主口
// 板级集成时：raw_vs/cam_valid/cam_raw 接厂商 CSI-2 RX 输出（valid 须按数据类型 0x2B 过滤），
// AXI 接 DDR3 控制器，APB 接 Sapphire SoC，视频输出接厂商 dvi_encoder，cam_en 经电平转换接摄像头使能脚
module vision_top #(
    // 摄像头
    // 0：RGB 每拍 2 像素（cam_scale3，仿真用）
    // 1：CSI RX RAW10 每拍 4 像素，3x3 分块去马赛克（SC431HAI 1920x1440）
    parameter CAM_RAW = 1,
    parameter IW = 1920, IH = 1440, XOFF = 0, CW = 1920,
    parameter GAMMA = "gamma_srgb.mem",
    // NN / 缓冲
    parameter NW = 640, NH = 480, STRIDE = 32'h200000, DW = 128, AW = 32, BL = 16, MBS = 16,
    parameter NN_ASYNC = 1,                 // NN 独立时钟（DDR 用户时钟偏低时仍可跑满帧率）
    // 显示（默认 1280x720@60）
    parameter H_ACT = 1280, H_FP = 110, H_SYNC = 40, H_BP = 220,
    parameter V_ACT = 720,  V_FP = 5,   V_SYNC = 5,  V_BP = 20,
    parameter VY0 = 120, SC = 2,
    parameter FONT = "font8x16.mem"
)(
    // 时钟复位
    input               clk_cam,
    input               clk_axi,
    input               clk_pix,
    input               clk_nn,
    input               rst_cam,
    input               rst_axi,
    input               rst_pix,
    // 摄像头：CAM_RAW=1 时为 CSI RX 输出（raw_vs、cam_valid、cam_raw 每拍 4 个 RAW10，p0 在低位）；
    //         CAM_RAW=0 时为 RGB 每拍 2 像素 {p1,p0}（每像素 {B,G,R}）+ 帧首 cam_sof
    input               cam_valid,
    input               cam_sof,
    input  [47:0]       cam_data,
    input               raw_vs,
    input  [39:0]       cam_raw,
    output              cam_en,             // 摄像头模组使能（寄存器 0x07C bit24，AXI 域准静态）
    // APB3 从机（与 clk_axi 同步）
    input  [11:0]       paddr,
    input               psel,
    input               penable,
    input               pwrite,
    input  [31:0]       pwdata,
    output [31:0]       prdata,
    output              pready,
    output              pslverr,
    output              irq,
    // AXI4 主口
    output [AW-1:0]     m_araddr,
    output [7:0]        m_arlen,
    output [2:0]        m_arsize,
    output [1:0]        m_arburst,
    output              m_arvalid,
    input               m_arready,
    input  [DW-1:0]     m_rdata,
    input               m_rlast,
    input               m_rvalid,
    output              m_rready,
    output [AW-1:0]     m_awaddr,
    output [7:0]        m_awlen,
    output [2:0]        m_awsize,
    output [1:0]        m_awburst,
    output              m_awvalid,
    input               m_awready,
    output [DW-1:0]     m_wdata,
    output [DW/8-1:0]   m_wstrb,
    output              m_wlast,
    output              m_wvalid,
    input               m_wready,
    input               m_bvalid,
    output              m_bready,
    // 视频输出（像素域）
    output              vid_hs,
    output              vid_vs,
    output              vid_de,
    output [7:0]        vid_r,
    output [7:0]        vid_g,
    output [7:0]        vid_b
);
    // ---------------- 摄像头域：降采样 → 跨域 FIFO ----------------
    wire        cs_v, cs_sof;
    wire [23:0] cs_d;
    wire [1:0]  bayer_a;
    wire [11:0] gr_a, gg_a, gb_a;
    wire [9:0]  blk_a;
    wire        gam_a;
    wire [1:0]  skip_a;
    generate
        if (CAM_RAW == 1) begin : g_raw
            // 相位与增益为准静态寄存器（AXI 域写入，摄像头域使用），按静态信号处理
            raw_bin3 #(.IW(IW), .IH(IH)) u_bin (
                .clk(clk_cam), .rst(rst_cam), .i_vs(raw_vs), .i_valid(cam_valid), .i_data(cam_raw),
                .bayer(bayer_a), .gain_r(gr_a), .gain_g(gg_a), .gain_b(gb_a),
                .o_valid(cs_v), .o_sof(cs_sof), .o_data(cs_d), .o_ready(1'b1));
        end else begin : g_rgb
            cam_scale3 #(.IW(IW), .IH(IH), .XOFF(XOFF), .CW(CW)) u_scale (
                .clk(clk_cam), .rst(rst_cam), .i_valid(cam_valid), .i_sof(cam_sof), .i_data(cam_data),
                .o_valid(cs_v), .o_sof(cs_sof), .o_data(cs_d));
        end
    endgenerate
    wire [24:0] cf_d;
    wire        cf_v, cf_r;
    afifo #(.W(25), .AW(10)) u_camf (
        .wclk(clk_cam), .wrst(rst_cam), .wdata({cs_sof, cs_d}), .wvalid(cs_v), .wready(), .wcount(),
        .rclk(clk_axi), .rrst(rst_axi), .rdata(cf_d), .rvalid(cf_v), .rready(cf_r));

    // ---------------- 显示域 ↔ AXI 域 ----------------
    wire [11:0] rq_d_p, rq_d_a;
    wire        rq_v_p, rq_v_a, rq_r_a;
    wire [23:0] vd_d_a, vd_d_p;
    wire        vd_v_a, vd_r_a, vd_v_p, vd_r_p;
    afifo #(.W(12), .AW(3)) u_reqf (
        .wclk(clk_pix), .wrst(rst_pix), .wdata(rq_d_p), .wvalid(rq_v_p), .wready(), .wcount(),
        .rclk(clk_axi), .rrst(rst_axi), .rdata(rq_d_a), .rvalid(rq_v_a), .rready(rq_r_a));
    afifo #(.W(24), .AW(11)) u_vidf (      // 2048 深（约 1.6 行），满时取数模块被反压
        .wclk(clk_axi), .wrst(rst_axi), .wdata(vd_d_a), .wvalid(vd_v_a), .wready(vd_r_a), .wcount(),
        .rclk(clk_pix), .rrst(rst_pix), .rdata(vd_d_p), .rvalid(vd_v_p), .rready(vd_r_p));

    // 准静态控制信号跨域（两级同步）
    wire [1:0]  mode_a;
    reg  [1:0]  mode_p1, mode_p2;
    always @(posedge clk_pix) begin mode_p1 <= mode_a; mode_p2 <= mode_p1; end
    wire [15:0] uf_p;
    reg  [15:0] uf_a1, uf_a2;
    always @(posedge clk_axi) begin uf_a1 <= uf_p; uf_a2 <= uf_a1; end

    // ---------------- APB3 → 寄存器总线 ----------------
    wire        bus_we = psel && penable && pwrite;
    wire [31:0] bus_rdata;
    assign prdata  = bus_rdata;
    assign pready  = 1'b1;
    assign pslverr = 1'b0;

    wire        osd_we;
    wire [10:0] osd_addr;
    wire [7:0]  osd_data;

    vision_core #(.NW(NW), .NH(NH), .STRIDE(STRIDE), .DW(DW), .AW(AW), .BL(BL), .MBS(MBS),
                  .NN_ASYNC(NN_ASYNC)) u_core (
        .clk(clk_axi), .rst(rst_axi), .clk_nn(clk_nn),
        .cam_data(cf_d[23:0]), .cam_sof(cf_d[24]), .cam_valid(cf_v), .cam_ready(cf_r),
        .req_data(rq_d_a), .req_valid(rq_v_a), .req_ready(rq_r_a),
        .vd_data(vd_d_a), .vd_valid(vd_v_a), .vd_ready(vd_r_a), .disp_frame(1'b0),
        .bus_we(bus_we), .bus_addr(paddr), .bus_wdata(pwdata), .bus_rdata(bus_rdata),
        .irq(irq), .disp_mode(mode_a), .cam_bayer(bayer_a), .cam_gr(gr_a), .cam_gg(gg_a), .cam_gb(gb_a),
        .cam_blk(blk_a), .cam_gamma(gam_a), .cam_skip(skip_a), .cam_en(cam_en),
        .osd_we(osd_we), .osd_addr(osd_addr), .osd_data(osd_data), .disp_underflow(uf_a2),
        .m_araddr(m_araddr), .m_arlen(m_arlen), .m_arsize(m_arsize), .m_arburst(m_arburst),
        .m_arvalid(m_arvalid), .m_arready(m_arready),
        .m_rdata(m_rdata), .m_rlast(m_rlast), .m_rvalid(m_rvalid), .m_rready(m_rready),
        .m_awaddr(m_awaddr), .m_awlen(m_awlen), .m_awsize(m_awsize), .m_awburst(m_awburst),
        .m_awvalid(m_awvalid), .m_awready(m_awready),
        .m_wdata(m_wdata), .m_wstrb(m_wstrb), .m_wlast(m_wlast), .m_wvalid(m_wvalid), .m_wready(m_wready),
        .m_bvalid(m_bvalid), .m_bready(m_bready));

    disp_core #(.H_ACT(H_ACT), .H_FP(H_FP), .H_SYNC(H_SYNC), .H_BP(H_BP),
                .V_ACT(V_ACT), .V_FP(V_FP), .V_SYNC(V_SYNC), .V_BP(V_BP),
                .VW(NW), .VH(NH), .VY0(VY0), .SC(SC), .FONT(FONT)) u_disp (
        .clk(clk_pix), .rst(rst_pix), .mode(mode_p2),
        .req_data(rq_d_p), .req_valid(rq_v_p),
        .f_data(vd_d_p), .f_valid(vd_v_p), .f_ready(vd_r_p),
        .osd_clk(clk_axi), .osd_we(osd_we), .osd_addr(osd_addr), .osd_data(osd_data),
        .o_hs(vid_hs), .o_vs(vid_vs), .o_de(vid_de), .o_r(vid_r), .o_g(vid_g), .o_b(vid_b),
        .underflow(uf_p), .frame_pulse());
endmodule
