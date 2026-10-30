// 结构生成来源：algo/gen_rtl.py；本文件为带PE12输出层和阅读注释的整机集成副本。
// 权重与系数RAM不带初值，开机由RISC-V从SPI Flash装载model/net_blob.bin。
// =============================================================================
// CNN网络顶层，整机层级：ti60f225_oob_top.engine.fast.net。
// 13个conv_layer是13套同时存在的流水硬件，各层内部再按通道/抽头分时运算。
// 这不是一套MAC依次执行13层；因此小参数模型仍会占用较多DSP和行缓存。
// 权重：各层mac内的wram（FPGA片内RAM）。WFILE=""仅表示不随位流初始化，
//       RAM仍被综合；启动后经cfg_*装载。此模块没有AXI/DDR读权重接口。
// 风格：共享卷积权重，style选择requant里的系数槽；NSTY=6为系数槽容量，
//       不代表六套卷积网络。当前整机调度送入风格0/1/2。
//
// 结构：e1 640x480->320x240；e2 ->160x120；r0..r3保持160x120；
//       d1a最近邻上采样->320x240；d1b/d2后由PixelShuffle输出640x480。
// 参数：GI/G为输入/输出每字通道数；PE为稠密卷积并行输出通道数；
//       DW=1为深度卷积；UP=1在滑窗取址中实现最近邻上采样；
//       FWD传递残差旁路，SKIP_ADD相加；R/S/S2是固定量化移位规则。
// 此处补充阅读注释；重新运行生成器时应保留同等说明。
// =============================================================================
module stylenet_top (
    // clk为150MHz推理时钟；rst清流水控制，不会清除已装入的权重RAM。
    input clk, input rst, input [3:0] style,
    // 配置口：cfg_layer选层；cfg_sel=1写权重、=0写系数。
    // cfg_lane选32位写入道，cfg_addr是层内RAM地址；上层只在任务间隙写入。
    input cfg_we, input cfg_sel, input [4:0] cfg_layer, input [4:0] cfg_lane,
    input [11:0] cfg_addr, input [37:0] cfg_data,
    // RGB24像素流，valid和ready同时为1才传输；输出反压可沿层间握手传播。
    input [23:0] i_data, input i_valid, output i_ready,
    output [23:0] o_data, output o_valid, input o_ready,
    // IN 统计（分时）：st_sel 选层，st_arm 预备，st_fs/st_fe 帧起止脉冲
    input [4:0] st_sel, input st_arm, input st_fs, input st_fe, input [7:0] st_idx,
    output [39:0] st_s1, output [59:0] st_s2, output st_done, output st_busy
);
    // dN为第N层的4通道UINT8输出字；sN携带残差旁路，vN/rN为握手。
    // svN/saN/scN是该层的IN统计抽头（有效、19位值、通道编号）。
    wire [31:0] d0, s0; wire v0, r0; wire sv0; wire [18:0] sa0; wire [7:0] sc0;
    wire [31:0] d1, s1; wire v1, r1; wire sv1; wire [18:0] sa1; wire [7:0] sc1;
    wire [31:0] d2, s2; wire v2, r2; wire sv2; wire [18:0] sa2; wire [7:0] sc2;
    wire [31:0] d3, s3; wire v3, r3; wire sv3; wire [18:0] sa3; wire [7:0] sc3;
    wire [31:0] d4, s4; wire v4, r4; wire sv4; wire [18:0] sa4; wire [7:0] sc4;
    wire [31:0] d5, s5; wire v5, r5; wire sv5; wire [18:0] sa5; wire [7:0] sc5;
    wire [31:0] d6, s6; wire v6, r6; wire sv6; wire [18:0] sa6; wire [7:0] sc6;
    wire [31:0] d7, s7; wire v7, r7; wire sv7; wire [18:0] sa7; wire [7:0] sc7;
    wire [31:0] d8, s8; wire v8, r8; wire sv8; wire [18:0] sa8; wire [7:0] sc8;
    wire [31:0] d9, s9; wire v9, r9; wire sv9; wire [18:0] sa9; wire [7:0] sc9;
    wire [31:0] d10, s10; wire v10, r10; wire sv10; wire [18:0] sa10; wire [7:0] sc10;
    wire [31:0] d11, s11; wire v11, r11; wire sv11; wire [18:0] sa11; wire [7:0] sc11;
    wire [31:0] d12, s12; wire v12, r12; wire sv12; wire [18:0] sa12; wire [7:0] sc12;
    // 第 0 层 e1：3x3稠密卷积，步长2；RGB3->16通道，PE4，12路乘法。
    conv_layer #(.K(3), .DW(0), .STRIDE(2), .UP(0), .GI(3), .CIN(3), .COUT(16), .G(4), .W(640), .H(480), .PE(4), .R(1), .S(20), .S2(8), .KSK(0), .SKIP_ADD(0), .FWD(0), .NSTY(6),
        .WFILE(""), .CFILE("")) u_l0 (
        .clk(clk), .rst(rst), .style(style),
        .cfg_we(cfg_we && cfg_layer == 0), .cfg_sel(cfg_sel), .cfg_lane(cfg_lane),
        .cfg_addr(cfg_addr), .cfg_data(cfg_data),
        .i_data(i_data), .i_side(24'd0), .i_valid(i_valid), .i_ready(i_ready),
        .o_data(d0), .o_side(s0), .o_valid(v0), .o_ready(r0),
        .st_v(sv0), .st_a(sa0), .st_ch(sc0));
    // 第 1 层 e2：3x3稠密卷积，步长2；16->24通道，PE4，16路乘法。
    conv_layer #(.K(3), .DW(0), .STRIDE(2), .UP(0), .GI(4), .CIN(16), .COUT(24), .G(4), .W(320), .H(240), .PE(4), .R(1), .S(21), .S2(8), .KSK(0), .SKIP_ADD(0), .FWD(0), .NSTY(6),
        .WFILE(""), .CFILE("")) u_l1 (
        .clk(clk), .rst(rst), .style(style),
        .cfg_we(cfg_we && cfg_layer == 1), .cfg_sel(cfg_sel), .cfg_lane(cfg_lane),
        .cfg_addr(cfg_addr), .cfg_data(cfg_data),
        .i_data(d0), .i_side(s0), .i_valid(v0), .i_ready(r0),
        .o_data(d1), .o_side(s1), .o_valid(v1), .o_ready(r1),
        .st_v(sv1), .st_a(sa1), .st_ch(sc1));
    // 第 2 层 r0a：残差块0的深度卷积，FWD=1把中心像素沿side前传。
    conv_layer #(.K(3), .DW(1), .STRIDE(1), .UP(0), .GI(4), .CIN(24), .COUT(24), .G(4), .W(160), .H(120), .PE(1), .R(0), .S(17), .S2(8), .KSK(0), .SKIP_ADD(0), .FWD(1), .NSTY(6),
        .WFILE(""), .CFILE("")) u_l2 (
        .clk(clk), .rst(rst), .style(style),
        .cfg_we(cfg_we && cfg_layer == 2), .cfg_sel(cfg_sel), .cfg_lane(cfg_lane),
        .cfg_addr(cfg_addr), .cfg_data(cfg_data),
        .i_data(d1), .i_side(s1), .i_valid(v1), .i_ready(r1),
        .o_data(d2), .o_side(s2), .o_valid(v2), .o_ready(r2),
        .st_v(sv2), .st_a(sa2), .st_ch(sc2));
    // 第 3 层 r0d：残差块0的1x1通道混合，SKIP_ADD=1加回side。
    conv_layer #(.K(1), .DW(0), .STRIDE(1), .UP(0), .GI(4), .CIN(24), .COUT(24), .G(4), .W(160), .H(120), .PE(1), .R(0), .S(17), .S2(8), .KSK(70950), .SKIP_ADD(1), .FWD(0), .NSTY(6),
        .WFILE(""), .CFILE("")) u_l3 (
        .clk(clk), .rst(rst), .style(style),
        .cfg_we(cfg_we && cfg_layer == 3), .cfg_sel(cfg_sel), .cfg_lane(cfg_lane),
        .cfg_addr(cfg_addr), .cfg_data(cfg_data),
        .i_data(d2), .i_side(s2), .i_valid(v2), .i_ready(r2),
        .o_data(d3), .o_side(s3), .o_valid(v3), .o_ready(r3),
        .st_v(sv3), .st_a(sa3), .st_ch(sc3));
    // 第 4 层 r1a：残差块1的3x3深度卷积，空间尺寸保持160x120。
    conv_layer #(.K(3), .DW(1), .STRIDE(1), .UP(0), .GI(4), .CIN(24), .COUT(24), .G(4), .W(160), .H(120), .PE(1), .R(0), .S(19), .S2(8), .KSK(0), .SKIP_ADD(0), .FWD(1), .NSTY(6),
        .WFILE(""), .CFILE("")) u_l4 (
        .clk(clk), .rst(rst), .style(style),
        .cfg_we(cfg_we && cfg_layer == 4), .cfg_sel(cfg_sel), .cfg_lane(cfg_lane),
        .cfg_addr(cfg_addr), .cfg_data(cfg_data),
        .i_data(d3), .i_side(s3), .i_valid(v3), .i_ready(r3),
        .o_data(d4), .o_side(s4), .o_valid(v4), .o_ready(r4),
        .st_v(sv4), .st_a(sa4), .st_ch(sc4));
    // 第 5 层 r1d：残差块1的1x1卷积及残差相加。
    conv_layer #(.K(1), .DW(0), .STRIDE(1), .UP(0), .GI(4), .CIN(24), .COUT(24), .G(4), .W(160), .H(120), .PE(1), .R(0), .S(17), .S2(8), .KSK(97034), .SKIP_ADD(1), .FWD(0), .NSTY(6),
        .WFILE(""), .CFILE("")) u_l5 (
        .clk(clk), .rst(rst), .style(style),
        .cfg_we(cfg_we && cfg_layer == 5), .cfg_sel(cfg_sel), .cfg_lane(cfg_lane),
        .cfg_addr(cfg_addr), .cfg_data(cfg_data),
        .i_data(d4), .i_side(s4), .i_valid(v4), .i_ready(r4),
        .o_data(d5), .o_side(s5), .o_valid(v5), .o_ready(r5),
        .st_v(sv5), .st_a(sa5), .st_ch(sc5));
    // 第 6 层 r2a：残差块2的3x3深度卷积。
    conv_layer #(.K(3), .DW(1), .STRIDE(1), .UP(0), .GI(4), .CIN(24), .COUT(24), .G(4), .W(160), .H(120), .PE(1), .R(0), .S(18), .S2(8), .KSK(0), .SKIP_ADD(0), .FWD(1), .NSTY(6),
        .WFILE(""), .CFILE("")) u_l6 (
        .clk(clk), .rst(rst), .style(style),
        .cfg_we(cfg_we && cfg_layer == 6), .cfg_sel(cfg_sel), .cfg_lane(cfg_lane),
        .cfg_addr(cfg_addr), .cfg_data(cfg_data),
        .i_data(d5), .i_side(s5), .i_valid(v5), .i_ready(r5),
        .o_data(d6), .o_side(s6), .o_valid(v6), .o_ready(r6),
        .st_v(sv6), .st_a(sa6), .st_ch(sc6));
    // 第 7 层 r2d：残差块2的1x1卷积及残差相加。
    conv_layer #(.K(1), .DW(0), .STRIDE(1), .UP(0), .GI(4), .CIN(24), .COUT(24), .G(4), .W(160), .H(120), .PE(1), .R(0), .S(17), .S2(8), .KSK(113384), .SKIP_ADD(1), .FWD(0), .NSTY(6),
        .WFILE(""), .CFILE("")) u_l7 (
        .clk(clk), .rst(rst), .style(style),
        .cfg_we(cfg_we && cfg_layer == 7), .cfg_sel(cfg_sel), .cfg_lane(cfg_lane),
        .cfg_addr(cfg_addr), .cfg_data(cfg_data),
        .i_data(d6), .i_side(s6), .i_valid(v6), .i_ready(r6),
        .o_data(d7), .o_side(s7), .o_valid(v7), .o_ready(r7),
        .st_v(sv7), .st_a(sa7), .st_ch(sc7));
    // 第 8 层 r3a：残差块3的3x3深度卷积。
    conv_layer #(.K(3), .DW(1), .STRIDE(1), .UP(0), .GI(4), .CIN(24), .COUT(24), .G(4), .W(160), .H(120), .PE(1), .R(0), .S(19), .S2(8), .KSK(0), .SKIP_ADD(0), .FWD(1), .NSTY(6),
        .WFILE(""), .CFILE("")) u_l8 (
        .clk(clk), .rst(rst), .style(style),
        .cfg_we(cfg_we && cfg_layer == 8), .cfg_sel(cfg_sel), .cfg_lane(cfg_lane),
        .cfg_addr(cfg_addr), .cfg_data(cfg_data),
        .i_data(d7), .i_side(s7), .i_valid(v7), .i_ready(r7),
        .o_data(d8), .o_side(s8), .o_valid(v8), .o_ready(r8),
        .st_v(sv8), .st_a(sa8), .st_ch(sc8));
    // 第 9 层 r3d：残差块3的1x1卷积及残差相加。
    conv_layer #(.K(1), .DW(0), .STRIDE(1), .UP(0), .GI(4), .CIN(24), .COUT(24), .G(4), .W(160), .H(120), .PE(1), .R(0), .S(18), .S2(8), .KSK(117607), .SKIP_ADD(1), .FWD(0), .NSTY(6),
        .WFILE(""), .CFILE("")) u_l9 (
        .clk(clk), .rst(rst), .style(style),
        .cfg_we(cfg_we && cfg_layer == 9), .cfg_sel(cfg_sel), .cfg_lane(cfg_lane),
        .cfg_addr(cfg_addr), .cfg_data(cfg_data),
        .i_data(d8), .i_side(s8), .i_valid(v8), .i_ready(r8),
        .o_data(d9), .o_side(s9), .o_valid(v9), .o_ready(r9),
        .st_v(sv9), .st_a(sa9), .st_ch(sc9));
    // 第 10 层 d1a：UP=1先按最近邻扩展2倍，再做深度卷积；不是双线性插值。
    conv_layer #(.K(3), .DW(1), .STRIDE(1), .UP(1), .GI(4), .CIN(24), .COUT(24), .G(4), .W(160), .H(120), .PE(1), .R(0), .S(20), .S2(8), .KSK(0), .SKIP_ADD(0), .FWD(0), .NSTY(6),
        .WFILE(""), .CFILE("")) u_l10 (
        .clk(clk), .rst(rst), .style(style),
        .cfg_we(cfg_we && cfg_layer == 10), .cfg_sel(cfg_sel), .cfg_lane(cfg_lane),
        .cfg_addr(cfg_addr), .cfg_data(cfg_data),
        .i_data(d9), .i_side(s9), .i_valid(v9), .i_ready(r9),
        .o_data(d10), .o_side(s10), .o_valid(v10), .o_ready(r10),
        .st_v(sv10), .st_a(sa10), .st_ch(sc10));
    // 第 11 层 d1b：320x240的1x1卷积，24->16通道，PE2。
    conv_layer #(.K(1), .DW(0), .STRIDE(1), .UP(0), .GI(4), .CIN(24), .COUT(16), .G(4), .W(320), .H(240), .PE(2), .R(0), .S(19), .S2(8), .KSK(0), .SKIP_ADD(0), .FWD(0), .NSTY(6),
        .WFILE(""), .CFILE("")) u_l11 (
        .clk(clk), .rst(rst), .style(style),
        .cfg_we(cfg_we && cfg_layer == 11), .cfg_sel(cfg_sel), .cfg_lane(cfg_lane),
        .cfg_addr(cfg_addr), .cfg_data(cfg_data),
        .i_data(d10), .i_side(s10), .i_valid(v10), .i_ready(r10),
        .o_data(d11), .o_side(s11), .o_valid(v11), .o_ready(r11),
        .st_v(sv11), .st_a(sa11), .st_ch(sc11));
    // 第 12 层 d2：输出3x3卷积，16->12通道，PE12 x GI4=48路乘法。
    // 权重每次片内读取384位；CFG_PE6保留原blob的装载道布局，非计算PE6。
    conv_layer #(.K(3), .DW(0), .STRIDE(1), .UP(0), .GI(4), .CIN(16), .COUT(12), .G(4), .W(320), .H(240), .PE(12), .CFG_PE(6), .R(1), .S(22), .S2(8), .KSK(0), .SKIP_ADD(0), .FWD(0), .NSTY(6),
        .WFILE(""), .CFILE("")) u_l12 (
        .clk(clk), .rst(rst), .style(style),
        .cfg_we(cfg_we && cfg_layer == 12), .cfg_sel(cfg_sel), .cfg_lane(cfg_lane),
        .cfg_addr(cfg_addr), .cfg_data(cfg_data),
        .i_data(d11), .i_side(s11), .i_valid(v11), .i_ready(r11),
        .o_data(d12), .o_side(s12), .o_valid(v12), .o_ready(r12),
        .st_v(sv12), .st_a(sa12), .st_ch(sc12));
    // 12个IN层共享一套统计累加器，st_sel逐帧选择统计层。
    // 输出层无IN，不接入统计选择器；统计单元不是13套逐层复制。
    reg tv; reg [18:0] ta; reg [7:0] tc;
    always @(*) begin
        tv = 1'b0; ta = 19'd0; tc = 8'd0;
        case (st_sel)
            5'd0: begin tv = sv0; ta = sa0; tc = sc0; end
            5'd1: begin tv = sv1; ta = sa1; tc = sc1; end
            5'd2: begin tv = sv2; ta = sa2; tc = sc2; end
            5'd3: begin tv = sv3; ta = sa3; tc = sc3; end
            5'd4: begin tv = sv4; ta = sa4; tc = sc4; end
            5'd5: begin tv = sv5; ta = sa5; tc = sc5; end
            5'd6: begin tv = sv6; ta = sa6; tc = sc6; end
            5'd7: begin tv = sv7; ta = sa7; tc = sc7; end
            5'd8: begin tv = sv8; ta = sa8; tc = sc8; end
            5'd9: begin tv = sv9; ta = sa9; tc = sc9; end
            5'd10: begin tv = sv10; ta = sa10; tc = sc10; end
            5'd11: begin tv = sv11; ta = sa11; tc = sc11; end
            // Layer 12 is the output pass: sc_engine selects 31 (no IN stats).
            // Excluding its unused PE12 accumulator tap removes a long mux path.
            default: ;
        endcase
    end
    in_stats #(.CMAX(24)) u_st (.clk(clk), .rst(rst), .arm(st_arm), .frame_start(st_fs),
        .frame_end(st_fe), .i_v(tv), .i_a(ta), .i_ch(tc), .rd_idx(st_idx),
        .rd_s1(st_s1), .rd_s2(st_s2), .done(st_done), .busy(st_busy));
    // PixelShuffle是通道重排：320x240x12 -> 640x480x3。
    // 内部缓存待输出的奇数行，保证光栅顺序；与摄像头的2x2平均缩小不同。
    pixshuf #(.WL(320), .HL(240)) u_ps (
        .clk(clk), .rst(rst), .i_data(d12), .i_valid(v12), .i_ready(r12),
        .o_data(o_data), .o_valid(o_valid), .o_ready(o_ready));
endmodule
