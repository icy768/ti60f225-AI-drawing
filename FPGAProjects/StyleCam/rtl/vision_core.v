// 视觉处理中枢（AXI 时钟域）
//   摄像头帧 → A 缓冲（4 个）；NN 取最新 A → 风格化 → B 缓冲（3 个）；显示按行读 A/B
//   缓冲选择避开：最新完成帧、NN 正在读的帧、显示当前帧正在读的帧，保证不撕裂、不丢当前帧
//   寄存器（字地址见下表），中断：bit0 NN 帧完成，bit1 摄像头帧完成
module vision_core #(
    parameter NW     = 640,          // NN / 缓冲帧宽
    parameter NH     = 480,
    parameter STRIDE = 32'h200000,   // 缓冲间距（字节）
    parameter DW     = 128,
    parameter AW     = 32,
    parameter BL     = 16,           // 突发拍数；NW 须为 (DW/32)*BL 的整数倍
    parameter MBS    = 16,           // 运动检测分块边长
    parameter NN_ASYNC = 0           // 1：NN 使用独立时钟 clk_nn
)(
    input                clk,
    input                rst,
    input                clk_nn,
    // 摄像头像素流（已跨入本时钟域）
    input  [23:0]        cam_data,
    input                cam_sof,
    input                cam_valid,
    output               cam_ready,
    // 显示行请求 / 视频 FIFO 写口
    input  [11:0]        req_data,
    input                req_valid,
    output               req_ready,
    output [23:0]        vd_data,
    output               vd_valid,
    input                vd_ready,
    input                disp_frame,     // 显示帧脉冲（已同步），仅计数用
    // 寄存器总线
    input                bus_we,
    input  [11:0]        bus_addr,       // 字节地址
    input  [31:0]        bus_wdata,
    output reg [31:0]    bus_rdata,
    output               irq,
    output [1:0]         disp_mode,
    output reg [1:0]     cam_bayer,      // 摄像头 Bayer 相位与白平衡增益（8.8）
    output reg [11:0]    cam_gr,
    output reg [11:0]    cam_gg,
    output reg [11:0]    cam_gb,
    output reg [9:0]     cam_blk,        // RAW 黑电平（旧传感器 为 64）
    output reg           cam_gamma,      // sRGB gamma 使能
    output reg [1:0]     cam_skip,       // 帧首跳过行数（跳过 CSI 嵌入数据行）
    output reg           cam_en,         // 摄像头模组使能（旧传感器 XCLR）
    output               osd_we,
    output [10:0]        osd_addr,
    output [7:0]         osd_data,
    input  [15:0]        disp_underflow,
    // AXI4 主口（至 DDR 控制器）
    output [AW-1:0]      m_araddr,
    output [7:0]         m_arlen,
    output [2:0]         m_arsize,
    output [1:0]         m_arburst,
    output               m_arvalid,
    input                m_arready,
    input  [DW-1:0]      m_rdata,
    input                m_rlast,
    input                m_rvalid,
    output               m_rready,
    output [AW-1:0]      m_awaddr,
    output [7:0]         m_awlen,
    output [2:0]         m_awsize,
    output [1:0]         m_awburst,
    output               m_awvalid,
    input                m_awready,
    output [DW-1:0]      m_wdata,
    output [DW/8-1:0]    m_wstrb,
    output               m_wlast,
    output               m_wvalid,
    input                m_wready,
    input                m_bvalid,
    output               m_bready
);
    localparam NPIX = NW * NH;
    localparam ROWB = NW * 4;
    assign m_arsize  = $clog2(DW / 8);
    assign m_awsize  = $clog2(DW / 8);
    assign m_arburst = 2'b01;
    assign m_awburst = 2'b01;

    // ================= 寄存器 =================
    // 0x000 ID  0x004 CTRL[0]nn_en [1]软复位 [3:2]显示模式  0x008 STYLE
    // 0x00C STATUS  0x010 CAM_FRAMES  0x014 NN_FRAMES  0x018 NN_CYCLES  0x01C DISP_FRAMES
    // 0x020 CFG_ADDR{[31]sel(0系数/1权重),[25:21]lane,[20:16]layer,[11:0]addr}  0x024 CFG_DLO  0x028 CFG_DHI(写即提交)
    // 0x02C BUF_BASE  0x030 IRQ_STATUS(写 1 清)  0x034 IRQ_EN  0x038 TIMER  0x03C UNDERFLOW
    // 0x040 STAT_CTRL 写:[4:0]层号并预备，读:[1]busy [0]done  0x044 STAT_IDX
    // 0x048/0x04C STAT_S1 低/高  0x050/0x054 STAT_S2 低/高（IN 统计，分时单层）
    // 0x058 MOT_TH  0x05C MOT_CNT  0x060 MOT_SX  0x064 MOT_SY  0x068 MOT_FRAMES（MBS 分块运动检测，挥手手势）
    // 0x06C CAM_BAYER[1:0]  0x070/0x074/0x078 白平衡增益 R/G/B（8.8，256=1.0）
    // 0x07C CAM_CTRL [9:0]黑电平 [12]gamma [17:16]帧首跳过行数 [24]模组使能
    // 0x080/0x084/0x088 CAM_SR/SG/SB 上一摄像头帧 R/G/B 之和  0x08C CAM_NHI 任一通道≥250 的像素数
    // 0x090 CAM_SSEQ 统计帧序号（AE/AWB 用，帧写完时更新）
    // 0x800-0xFFF OSD 文字（每字 4 个字符，低字节在前）
    reg        nn_en, sw_rst;
    reg [1:0]  mode_r;
    reg [3:0]  style_r;
    reg [31:0] cfg_addr_r, cfg_dlo, buf_base, timer;
    reg [1:0]  irq_st, irq_en;
    reg [31:0] cam_frames, nn_frames, nn_cycles, disp_frames;
    reg        cfg_we;
    reg [5:0]  cfg_dhi;
    reg [4:0]  st_sel;
    reg        st_arm;
    reg [7:0]  st_idx;
    wire [39:0] st_s1;
    wire [59:0] st_s2;
    wire       st_done, st_busy;
    reg [7:0]  mot_th;
    wire [15:0] mot_cnt;
    wire [23:0] mot_sx, mot_sy;
    wire       mot_done;
    reg [31:0] mot_frames;
    reg [26:0] cam_sr, cam_sg, cam_sb;   // 摄像头帧统计（锁存值）
    reg [18:0] cam_nhi;
    reg [15:0] cam_sseq;
    wire       nn_done_evt, cam_done_evt;
    wire       core_rst = rst || sw_rst;
    assign disp_mode = mode_r;
    assign irq = |(irq_st & irq_en);
    // OSD：每次写 1 个 32 位字（4 个字符，低字节在前），随后 4 拍逐字节写入文字 RAM
    // （CPU 经 APB 的两次写之间远多于 4 拍）
    reg [31:0] osd_word;
    reg [10:0] osd_base;
    reg [2:0]  osd_cnt;
    always @(posedge clk) begin
        if (rst) osd_cnt <= 0;
        else if (bus_we && bus_addr[11]) begin
            osd_word <= bus_wdata;
            osd_base <= {bus_addr[10:2], 2'b00};
            osd_cnt  <= 3'd4;
        end else if (osd_cnt != 0) begin
            osd_word <= osd_word >> 8;
            osd_base <= osd_base + 1'b1;
            osd_cnt  <= osd_cnt - 1'b1;
        end
    end
    assign osd_we   = (osd_cnt != 0);
    assign osd_addr = osd_base;
    assign osd_data = osd_word[7:0];
    reg        nn_busy, cam_busy;
    always @(posedge clk) begin
        if (rst) begin
            nn_en <= 0; sw_rst <= 0; mode_r <= 0; style_r <= 0; buf_base <= 0;
            irq_st <= 0; irq_en <= 0; cfg_we <= 0; timer <= 0; st_sel <= 0; st_arm <= 0; st_idx <= 0;
            mot_th <= 8'd12; mot_frames <= 0;
            cam_bayer <= 2'd0; cam_gr <= 12'd440; cam_gg <= 12'd273; cam_gb <= 12'd420;
            cam_blk <= 10'd64; cam_gamma <= 1'b1; cam_skip <= 2'd0; cam_en <= 1'b0;
        end else begin
            timer  <= timer + 1;
            sw_rst <= 1'b0;
            cfg_we <= 1'b0;
            st_arm <= 1'b0;
            if (bus_we && !bus_addr[11]) case (bus_addr[7:0])
                8'h40: begin st_sel <= bus_wdata[4:0]; st_arm <= 1'b1; end
                8'h44: st_idx <= bus_wdata[7:0];
                8'h58: mot_th <= bus_wdata[7:0];
                8'h6C: cam_bayer <= bus_wdata[1:0];
                8'h70: cam_gr <= bus_wdata[11:0];
                8'h74: cam_gg <= bus_wdata[11:0];
                8'h78: cam_gb <= bus_wdata[11:0];
                8'h7C: begin
                    cam_blk <= bus_wdata[9:0]; cam_gamma <= bus_wdata[12];
                    cam_skip <= bus_wdata[17:16]; cam_en <= bus_wdata[24];
                end
                8'h04: begin nn_en <= bus_wdata[0]; sw_rst <= bus_wdata[1]; mode_r <= bus_wdata[3:2]; end
                8'h08: style_r <= bus_wdata[3:0];
                8'h20: cfg_addr_r <= bus_wdata;
                8'h24: cfg_dlo <= bus_wdata;
                8'h28: begin cfg_dhi <= bus_wdata[5:0]; cfg_we <= 1'b1; end
                8'h2C: buf_base <= bus_wdata;
                8'h30: irq_st <= irq_st & ~bus_wdata[1:0];
                8'h34: irq_en <= bus_wdata[1:0];
                default: ;
            endcase
            if (mot_done) mot_frames <= mot_frames + 1;
            if (nn_done_evt)  irq_st[0] <= 1'b1;
            if (cam_done_evt) irq_st[1] <= 1'b1;
        end
    end
    always @(*) begin
        case (bus_addr[7:0])
            8'h00: bus_rdata = 32'h53544C31;           // "STL1"
            8'h04: bus_rdata = {28'd0, mode_r, 1'b0, nn_en};
            8'h08: bus_rdata = {28'd0, style_r};
            8'h0C: bus_rdata = {30'd0, cam_busy, nn_busy};
            8'h10: bus_rdata = cam_frames;
            8'h14: bus_rdata = nn_frames;
            8'h18: bus_rdata = nn_cycles;
            8'h1C: bus_rdata = disp_frames;
            8'h20: bus_rdata = cfg_addr_r;
            8'h2C: bus_rdata = buf_base;
            8'h30: bus_rdata = {30'd0, irq_st};
            8'h34: bus_rdata = {30'd0, irq_en};
            8'h38: bus_rdata = timer;
            8'h3C: bus_rdata = {16'd0, disp_underflow};
            8'h40: bus_rdata = {30'd0, st_busy, st_done};
            8'h44: bus_rdata = {24'd0, st_idx};
            8'h48: bus_rdata = st_s1[31:0];
            8'h4C: bus_rdata = {{24{st_s1[39]}}, st_s1[39:32]};
            8'h50: bus_rdata = st_s2[31:0];
            8'h54: bus_rdata = {4'd0, st_s2[59:32]};
            8'h58: bus_rdata = {24'd0, mot_th};
            8'h5C: bus_rdata = {16'd0, mot_cnt};
            8'h60: bus_rdata = {8'd0, mot_sx};
            8'h64: bus_rdata = {8'd0, mot_sy};
            8'h68: bus_rdata = mot_frames;
            8'h6C: bus_rdata = {30'd0, cam_bayer};
            8'h70: bus_rdata = {20'd0, cam_gr};
            8'h74: bus_rdata = {20'd0, cam_gg};
            8'h78: bus_rdata = {20'd0, cam_gb};
            8'h7C: bus_rdata = {7'd0, cam_en, 6'd0, cam_skip, 3'd0, cam_gamma, 2'd0, cam_blk};
            8'h80: bus_rdata = {5'd0, cam_sr};
            8'h84: bus_rdata = {5'd0, cam_sg};
            8'h88: bus_rdata = {5'd0, cam_sb};
            8'h8C: bus_rdata = {13'd0, cam_nhi};
            8'h90: bus_rdata = {16'd0, cam_sseq};
            default: bus_rdata = 32'd0;
        endcase
    end

    // ================= 缓冲管理 =================
    reg [1:0] a_latest, a_nn, a_disp, a_wr;
    reg       a_latest_v, a_nn_v, a_disp_v;
    reg [1:0] b_latest, b_disp, b_wr;
    reg       b_latest_v, b_disp_v;
    reg [31:0] a_seq, a_seq_nn;
    function [1:0] pick_a(input [1:0] x0, input v0, input [1:0] x1, input v1, input [1:0] x2, input v2);
        integer k;
        begin
            pick_a = 0;
            for (k = 3; k >= 0; k = k - 1)
                if (!((v0 && x0 == k) || (v1 && x1 == k) || (v2 && x2 == k))) pick_a = k;
        end
    endfunction
    function [1:0] pick_b(input [1:0] x0, input v0, input [1:0] x1, input v1);
        integer k;
        begin
            pick_b = 0;
            for (k = 2; k >= 0; k = k - 1)
                if (!((v0 && x0 == k) || (v1 && x1 == k))) pick_b = k;
        end
    endfunction
    wire [AW-1:0] a_addr_wr = buf_base + a_wr * STRIDE;

    // ================= AXI 主机 =================
    wire [2*AW-1:0] ar_addr, aw_addr;
    wire [15:0]     ar_len, aw_len;
    wire [1:0]      ar_valid, ar_ready, r_valid, r_ready;
    wire [1:0]      aw_valid, aw_ready, w_last, w_valid, w_ready, b_valid, b_ready;
    wire [2*DW-1:0] w_data;
    wire [2*DW/8-1:0] w_strb;
    wire [DW-1:0]   r_data;
    wire            r_last;

    // ---- 摄像头写（写口 0）----
    reg        cw_start;
    wire       cw_busy, cw_done;
    wire [23:0] cw_d;
    wire       cw_v, cw_r;
    reg        cam_stream;
    // 等待帧首：非帧首像素直接丢弃
    assign cam_ready = cam_stream ? cw_r : (cam_valid && !cam_sof && !cw_start);
    assign cw_v = cam_stream && cam_valid;
    axi_frame_wr #(.DW(DW), .AW(AW), .BL(BL)) u_camw (
        .clk(clk), .rst(core_rst), .start(cw_start), .base(a_addr_wr), .npix(NPIX),
        .busy(cw_busy), .done(cw_done),
        .s_data(cam_data), .s_valid(cw_v), .s_ready(cw_r),
        .awid(), .awaddr(aw_addr[0 +: AW]), .awlen(aw_len[0 +: 8]), .awsize(), .awburst(),
        .awvalid(aw_valid[0]), .awready(aw_ready[0]),
        .wdata(w_data[0 +: DW]), .wstrb(w_strb[0 +: DW/8]), .wlast(w_last[0]),
        .wvalid(w_valid[0]), .wready(w_ready[0]),
        .bid(4'd0), .bresp(2'd0), .bvalid(b_valid[0]), .bready(b_ready[0]));
    assign cam_done_evt = cw_done;
    // 运动检测：取写入 DDR 的摄像头像素流
    // 摄像头帧统计（AE/AWB）：与运动检测取同一像素流，帧首清零、帧写完锁存
    wire        cam_go = !cam_stream && !cw_start && cam_valid && cam_sof;
    wire        cs_en  = cam_valid && cam_ready && cam_stream;
    wire        cs_hi  = (cam_data[7:0] >= 8'd250) || (cam_data[15:8] >= 8'd250) || (cam_data[23:16] >= 8'd250);
    reg  [26:0] sr_acc, sg_acc, sb_acc;
    reg  [18:0] hi_acc;
    always @(posedge clk) begin
        if (core_rst) begin
            sr_acc <= 0; sg_acc <= 0; sb_acc <= 0; hi_acc <= 0;
            cam_sr <= 0; cam_sg <= 0; cam_sb <= 0; cam_nhi <= 0; cam_sseq <= 0;
        end else begin
            if (cam_go) begin
                sr_acc <= 0; sg_acc <= 0; sb_acc <= 0; hi_acc <= 0;
            end else if (cs_en) begin
                sr_acc <= sr_acc + cam_data[7:0];
                sg_acc <= sg_acc + cam_data[15:8];
                sb_acc <= sb_acc + cam_data[23:16];
                hi_acc <= hi_acc + cs_hi;
            end
            if (cw_done) begin
                cam_sr <= sr_acc; cam_sg <= sg_acc; cam_sb <= sb_acc; cam_nhi <= hi_acc;
                cam_sseq <= cam_sseq + 1'b1;
            end
        end
    end
    motion_det #(.W(NW), .H(NH), .BS(MBS)) u_mot (
        .clk(clk), .rst(core_rst), .i_valid(cam_valid && cam_ready && cam_stream), .i_sof(cam_sof),
        .i_data(cam_data), .th(mot_th), .m_cnt(mot_cnt), .m_sx(mot_sx), .m_sy(mot_sy), .frame_done(mot_done));

    // ---- NN：读口 0 → stylenet → 写口 1 ----
    reg        nn_start;
    reg [3:0]  nn_style;
    wire       nr_busy, nr_done, nw_busy, nw_done;
    wire [23:0] nr_d, nn_od;
    wire       nr_v, nr_r, nn_ov, nn_or;
    reg [31:0] nn_cyc;
    axi_frame_rd #(.DW(DW), .AW(AW), .BL(BL)) u_nnr (
        .clk(clk), .rst(core_rst), .start(nn_start), .base(buf_base + a_nn * STRIDE), .npix(NPIX),
        .busy(nr_busy), .done(nr_done),
        .m_data(nr_d), .m_valid(nr_v), .m_ready(nr_r),
        .arid(), .araddr(ar_addr[0 +: AW]), .arlen(ar_len[0 +: 8]), .arsize(), .arburst(),
        .arvalid(ar_valid[0]), .arready(ar_ready[0]),
        .rid(4'd0), .rdata(r_data), .rresp(2'd0), .rlast(r_last), .rvalid(r_valid[0]), .rready(r_ready[0]));
    // NN 可工作在独立时钟 clk_nn（NN_ASYNC=1）：数据流经异步 FIFO，控制脉冲经翻转同步；
    // 风格号、cfg 地址/数据、统计读出在使用期间保持不变，按静态信号处理（综合时设 false path）
    wire [23:0] ni_d, no_d;
    wire        ni_v, ni_r, no_v, no_r;
    wire        n_rst, n_cfg_we, n_arm, n_fs, n_fe, n_done, n_busy;
    generate
        if (NN_ASYNC) begin : g_nn_async
            reg [1:0] rs;
            always @(posedge clk_nn or posedge core_rst) rs <= core_rst ? 2'b11 : {rs[0], 1'b0};
            assign n_rst = rs[1];
            afifo #(.W(24), .AW(4)) u_ni (
                .wclk(clk), .wrst(core_rst), .wdata(nr_d), .wvalid(nr_v), .wready(nr_r), .wcount(),
                .rclk(clk_nn), .rrst(n_rst), .rdata(ni_d), .rvalid(ni_v), .rready(ni_r));
            afifo #(.W(24), .AW(4)) u_no (
                .wclk(clk_nn), .wrst(n_rst), .wdata(no_d), .wvalid(no_v), .wready(no_r), .wcount(),
                .rclk(clk), .rrst(core_rst), .rdata(nn_od), .rvalid(nn_ov), .rready(nn_or));
            pulse_sync u_p0 (.sclk(clk), .srst(core_rst), .spulse(cfg_we),   .dclk(clk_nn), .drst(n_rst), .dpulse(n_cfg_we));
            pulse_sync u_p1 (.sclk(clk), .srst(core_rst), .spulse(st_arm),   .dclk(clk_nn), .drst(n_rst), .dpulse(n_arm));
            pulse_sync u_p2 (.sclk(clk), .srst(core_rst), .spulse(nn_start), .dclk(clk_nn), .drst(n_rst), .dpulse(n_fs));
            pulse_sync u_p3 (.sclk(clk), .srst(core_rst), .spulse(nw_done),  .dclk(clk_nn), .drst(n_rst), .dpulse(n_fe));
            bit_sync u_b0 (.dclk(clk), .d(n_done), .q(st_done));
            bit_sync u_b1 (.dclk(clk), .d(n_busy), .q(st_busy));
        end else begin : g_nn_sync
            assign n_rst = core_rst;
            assign ni_d = nr_d; assign ni_v = nr_v; assign nr_r = ni_r;
            assign nn_od = no_d; assign nn_ov = no_v; assign no_r = nn_or;
            assign n_cfg_we = cfg_we; assign n_arm = st_arm; assign n_fs = nn_start; assign n_fe = nw_done;
            assign st_done = n_done; assign st_busy = n_busy;
        end
    endgenerate
    stylenet_top u_net (
        .clk(NN_ASYNC ? clk_nn : clk), .rst(n_rst), .style(nn_style),
        .cfg_we(n_cfg_we), .cfg_sel(cfg_addr_r[31]), .cfg_layer(cfg_addr_r[16 +: 5]),
        .cfg_lane(cfg_addr_r[21 +: 5]), .cfg_addr(cfg_addr_r[11:0]), .cfg_data({cfg_dhi, cfg_dlo}),
        .i_data(ni_d), .i_valid(ni_v), .i_ready(ni_r),
        .o_data(no_d), .o_valid(no_v), .o_ready(no_r),
        .st_sel(st_sel), .st_arm(n_arm), .st_fs(n_fs), .st_fe(n_fe), .st_idx(st_idx),
        .st_s1(st_s1), .st_s2(st_s2), .st_done(n_done), .st_busy(n_busy));
    axi_frame_wr #(.DW(DW), .AW(AW), .BL(BL)) u_nnw (
        .clk(clk), .rst(core_rst), .start(nn_start), .base(buf_base + (4 + b_wr) * STRIDE), .npix(NPIX),
        .busy(nw_busy), .done(nw_done),
        .s_data(nn_od), .s_valid(nn_ov), .s_ready(nn_or),
        .awid(), .awaddr(aw_addr[AW +: AW]), .awlen(aw_len[8 +: 8]), .awsize(), .awburst(),
        .awvalid(aw_valid[1]), .awready(aw_ready[1]),
        .wdata(w_data[DW +: DW]), .wstrb(w_strb[DW/8 +: DW/8]), .wlast(w_last[1]),
        .wvalid(w_valid[1]), .wready(w_ready[1]),
        .bid(4'd0), .bresp(2'd0), .bvalid(b_valid[1]), .bready(b_ready[1]));
    assign nn_done_evt = nw_done;

    // ---- 显示取数：读口 1 ----
    // 每个行请求取 1 段（模式 1/2）或 2 段（模式 0：原图段 + 风格图段），每段 NW 像素；
    // 对应缓冲尚无有效帧时以黑色填充，不读 DDR
    reg        dr_start, dr_run, dr_seg, zrun, dr_launch;
    reg [AW-1:0] dr_base;
    reg [10:0] dr_line;
    reg [1:0]  dr_mode;
    reg [15:0] zcnt;
    wire       dr_busy, dr_done;
    wire [23:0] rd_d;
    wire       rd_v, rd_r;
    reg        req_take;
    assign req_ready = req_take;
    assign vd_data  = zrun ? 24'h000000 : rd_d;
    assign vd_valid = zrun ? 1'b1 : rd_v;
    assign rd_r     = !zrun && vd_ready;
    wire zdone = zrun && vd_ready && (zcnt == NW - 1);
    axi_frame_rd #(.DW(DW), .AW(AW), .BL(BL)) u_dr (
        .clk(clk), .rst(core_rst), .start(dr_start), .base(dr_base), .npix(NW),
        .busy(dr_busy), .done(dr_done),
        .m_data(rd_d), .m_valid(rd_v), .m_ready(rd_r),
        .arid(), .araddr(ar_addr[AW +: AW]), .arlen(ar_len[8 +: 8]), .arsize(), .arburst(),
        .arvalid(ar_valid[1]), .arready(ar_ready[1]),
        .rid(4'd0), .rdata(r_data), .rresp(2'd0), .rlast(r_last), .rvalid(r_valid[1]), .rready(r_ready[1]));
    // 段 s 用哪个缓冲：模式 0 段 0 与模式 2 为原图，其余为风格图
    wire       seg_is_b  = (dr_mode == 1) || (dr_mode == 0 && dr_seg);
    wire       seg_valid = seg_is_b ? b_disp_v : a_disp_v;

    axi_arb #(.NR(2), .NW(2), .DW(DW), .AW(AW)) u_arb (
        .clk(clk), .rst(core_rst),
        .m_araddr(ar_addr), .m_arlen(ar_len), .m_arvalid(ar_valid), .m_arready(ar_ready),
        .m_rdata(r_data), .m_rlast(r_last), .m_rresp(), .m_rvalid(r_valid), .m_rready(r_ready),
        .m_awaddr(aw_addr), .m_awlen(aw_len), .m_awvalid(aw_valid), .m_awready(aw_ready),
        .m_wdata(w_data), .m_wstrb(w_strb), .m_wlast(w_last), .m_wvalid(w_valid), .m_wready(w_ready),
        .m_bvalid(b_valid), .m_bready(b_ready),
        .s_araddr(m_araddr), .s_arlen(m_arlen), .s_arvalid(m_arvalid), .s_arready(m_arready),
        .s_rdata(m_rdata), .s_rlast(m_rlast), .s_rresp(2'd0), .s_rvalid(m_rvalid), .s_rready(m_rready),
        .s_awaddr(m_awaddr), .s_awlen(m_awlen), .s_awvalid(m_awvalid), .s_awready(m_awready),
        .s_wdata(m_wdata), .s_wstrb(m_wstrb), .s_wlast(m_wlast), .s_wvalid(m_wvalid), .s_wready(m_wready),
        .s_bvalid(m_bvalid), .s_bready(m_bready));

    // ================= 控制 =================
    always @(posedge clk) begin
        if (core_rst) begin
            cw_start <= 0; cam_stream <= 0; cam_busy <= 0;
            nn_start <= 0; nn_busy <= 0;
            a_latest_v <= 0; a_nn_v <= 0; a_disp_v <= 0; b_latest_v <= 0; b_disp_v <= 0;
            a_seq <= 0; a_seq_nn <= 0;
            dr_start <= 0; dr_run <= 0; req_take <= 0; dr_launch <= 0; zrun <= 0; dr_mode <= 0;
            a_disp <= 0; b_disp <= 0; a_nn <= 0; a_latest <= 0; b_latest <= 0;
            cam_frames <= 0; nn_frames <= 0; disp_frames <= 0; nn_cycles <= 0;
        end else begin
            cw_start <= 1'b0;
            nn_start <= 1'b0;
            dr_start <= 1'b0;
            req_take <= 1'b0;
            // ---- 摄像头 ----
            if (!cam_stream && !cw_start && cam_valid && cam_sof) begin
                a_wr     <= pick_a(a_latest, a_latest_v, a_nn, a_nn_v, a_disp, a_disp_v);
                cw_start <= 1'b1;
                cam_stream <= 1'b1;
                cam_busy <= 1'b1;
            end
            if (cw_done) begin
                cam_stream <= 1'b0;
                cam_busy <= 1'b0;
                a_latest <= a_wr;
                a_latest_v <= 1'b1;
                a_seq <= a_seq + 1;
                cam_frames <= cam_frames + 1;
            end
            // ---- NN ----
            if (nn_busy) nn_cyc <= nn_cyc + 1;
            if (!nn_busy && !nn_start && nn_en && a_latest_v && a_seq != a_seq_nn && !cw_done) begin
                a_nn     <= a_latest;
                a_nn_v   <= 1'b1;
                a_seq_nn <= a_seq;
                b_wr     <= pick_b(b_latest, b_latest_v, b_disp, b_disp_v);
                nn_style <= style_r;                 // 帧边界锁存风格，切换不撕裂
                nn_start <= 1'b1;
                nn_busy  <= 1'b1;
                nn_cyc   <= 0;
            end
            if (nw_done) begin
                nn_busy <= 1'b0;
                a_nn_v  <= 1'b0;
                b_latest <= b_wr;
                b_latest_v <= 1'b1;
                nn_frames <= nn_frames + 1;
                nn_cycles <= nn_cyc;
            end
            // ---- 显示取数 ----
            if (zrun && vd_ready) zcnt <= zcnt + 1'b1;
            if (!dr_run && !dr_start && req_valid && !req_take) begin
                req_take <= 1'b1;
                if (req_data[11]) begin
                    // 帧请求：锁定本帧显示用的 A/B 缓冲与模式
                    a_disp <= a_latest; a_disp_v <= a_latest_v;
                    b_disp <= b_latest; b_disp_v <= b_latest_v;
                    dr_mode <= disp_mode;
                    disp_frames <= disp_frames + 1;
                end else begin
                    dr_line <= req_data[10:0];
                    dr_seg  <= 1'b0;
                    dr_run  <= 1'b1;
                    dr_launch <= 1'b1;
                end
            end
            // 发起一段：有效则读 DDR，否则填黑
            if (dr_launch) begin
                dr_launch <= 1'b0;
                if (seg_valid) begin
                    dr_start <= 1'b1;
                    dr_base  <= buf_base + (seg_is_b ? (4 + b_disp) : a_disp) * STRIDE + dr_line * ROWB;
                end else begin
                    zrun <= 1'b1;
                    zcnt <= 0;
                end
            end
            if (zdone) zrun <= 1'b0;
            if (dr_run && (dr_done || zdone)) begin
                if (dr_mode == 0 && !dr_seg) begin
                    dr_seg    <= 1'b1;
                    dr_launch <= 1'b1;
                end else
                    dr_run <= 1'b0;
            end
        end
    end
endmodule
