// 自动生成：algo/gen_rtl.py，勿手改
module stylenet_top (
    input clk, input rst, input [3:0] style,
    input cfg_we, input cfg_sel, input [4:0] cfg_layer, input [4:0] cfg_lane,
    input [11:0] cfg_addr, input [37:0] cfg_data,
    input [23:0] i_data, input i_valid, output i_ready,
    output [23:0] o_data, output o_valid, input o_ready,
    // IN 统计（分时）：st_sel 选层，st_arm 预备，st_fs/st_fe 帧起止脉冲
    input [4:0] st_sel, input st_arm, input st_fs, input st_fe, input [7:0] st_idx,
    output [39:0] st_s1, output [59:0] st_s2, output st_done, output st_busy
);
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
    // 第 0 层 e1
    conv_layer #(.K(3), .DW(0), .STRIDE(2), .UP(0), .GI(3), .CIN(3), .COUT(16), .G(4), .W(48), .H(32), .PE(4), .R(1), .S(20), .S2(8), .KSK(0), .SKIP_ADD(0), .FWD(0), .NSTY(6),
        .WFILE(""), .CFILE("")) u_l0 (
        .clk(clk), .rst(rst), .style(style),
        .cfg_we(cfg_we && cfg_layer == 0), .cfg_sel(cfg_sel), .cfg_lane(cfg_lane),
        .cfg_addr(cfg_addr), .cfg_data(cfg_data),
        .i_data(i_data), .i_side(24'd0), .i_valid(i_valid), .i_ready(i_ready),
        .o_data(d0), .o_side(s0), .o_valid(v0), .o_ready(r0),
        .st_v(sv0), .st_a(sa0), .st_ch(sc0));
    // 第 1 层 e2
    conv_layer #(.K(3), .DW(0), .STRIDE(2), .UP(0), .GI(4), .CIN(16), .COUT(24), .G(4), .W(24), .H(16), .PE(4), .R(1), .S(21), .S2(8), .KSK(0), .SKIP_ADD(0), .FWD(0), .NSTY(6),
        .WFILE(""), .CFILE("")) u_l1 (
        .clk(clk), .rst(rst), .style(style),
        .cfg_we(cfg_we && cfg_layer == 1), .cfg_sel(cfg_sel), .cfg_lane(cfg_lane),
        .cfg_addr(cfg_addr), .cfg_data(cfg_data),
        .i_data(d0), .i_side(s0), .i_valid(v0), .i_ready(r0),
        .o_data(d1), .o_side(s1), .o_valid(v1), .o_ready(r1),
        .st_v(sv1), .st_a(sa1), .st_ch(sc1));
    // 第 2 层 r0a
    conv_layer #(.K(3), .DW(1), .STRIDE(1), .UP(0), .GI(4), .CIN(24), .COUT(24), .G(4), .W(12), .H(8), .PE(1), .R(0), .S(17), .S2(8), .KSK(0), .SKIP_ADD(0), .FWD(1), .NSTY(6),
        .WFILE(""), .CFILE("")) u_l2 (
        .clk(clk), .rst(rst), .style(style),
        .cfg_we(cfg_we && cfg_layer == 2), .cfg_sel(cfg_sel), .cfg_lane(cfg_lane),
        .cfg_addr(cfg_addr), .cfg_data(cfg_data),
        .i_data(d1), .i_side(s1), .i_valid(v1), .i_ready(r1),
        .o_data(d2), .o_side(s2), .o_valid(v2), .o_ready(r2),
        .st_v(sv2), .st_a(sa2), .st_ch(sc2));
    // 第 3 层 r0d
    conv_layer #(.K(1), .DW(0), .STRIDE(1), .UP(0), .GI(4), .CIN(24), .COUT(24), .G(4), .W(12), .H(8), .PE(1), .R(0), .S(17), .S2(8), .KSK(70950), .SKIP_ADD(1), .FWD(0), .NSTY(6),
        .WFILE(""), .CFILE("")) u_l3 (
        .clk(clk), .rst(rst), .style(style),
        .cfg_we(cfg_we && cfg_layer == 3), .cfg_sel(cfg_sel), .cfg_lane(cfg_lane),
        .cfg_addr(cfg_addr), .cfg_data(cfg_data),
        .i_data(d2), .i_side(s2), .i_valid(v2), .i_ready(r2),
        .o_data(d3), .o_side(s3), .o_valid(v3), .o_ready(r3),
        .st_v(sv3), .st_a(sa3), .st_ch(sc3));
    // 第 4 层 r1a
    conv_layer #(.K(3), .DW(1), .STRIDE(1), .UP(0), .GI(4), .CIN(24), .COUT(24), .G(4), .W(12), .H(8), .PE(1), .R(0), .S(19), .S2(8), .KSK(0), .SKIP_ADD(0), .FWD(1), .NSTY(6),
        .WFILE(""), .CFILE("")) u_l4 (
        .clk(clk), .rst(rst), .style(style),
        .cfg_we(cfg_we && cfg_layer == 4), .cfg_sel(cfg_sel), .cfg_lane(cfg_lane),
        .cfg_addr(cfg_addr), .cfg_data(cfg_data),
        .i_data(d3), .i_side(s3), .i_valid(v3), .i_ready(r3),
        .o_data(d4), .o_side(s4), .o_valid(v4), .o_ready(r4),
        .st_v(sv4), .st_a(sa4), .st_ch(sc4));
    // 第 5 层 r1d
    conv_layer #(.K(1), .DW(0), .STRIDE(1), .UP(0), .GI(4), .CIN(24), .COUT(24), .G(4), .W(12), .H(8), .PE(1), .R(0), .S(17), .S2(8), .KSK(97034), .SKIP_ADD(1), .FWD(0), .NSTY(6),
        .WFILE(""), .CFILE("")) u_l5 (
        .clk(clk), .rst(rst), .style(style),
        .cfg_we(cfg_we && cfg_layer == 5), .cfg_sel(cfg_sel), .cfg_lane(cfg_lane),
        .cfg_addr(cfg_addr), .cfg_data(cfg_data),
        .i_data(d4), .i_side(s4), .i_valid(v4), .i_ready(r4),
        .o_data(d5), .o_side(s5), .o_valid(v5), .o_ready(r5),
        .st_v(sv5), .st_a(sa5), .st_ch(sc5));
    // 第 6 层 r2a
    conv_layer #(.K(3), .DW(1), .STRIDE(1), .UP(0), .GI(4), .CIN(24), .COUT(24), .G(4), .W(12), .H(8), .PE(1), .R(0), .S(18), .S2(8), .KSK(0), .SKIP_ADD(0), .FWD(1), .NSTY(6),
        .WFILE(""), .CFILE("")) u_l6 (
        .clk(clk), .rst(rst), .style(style),
        .cfg_we(cfg_we && cfg_layer == 6), .cfg_sel(cfg_sel), .cfg_lane(cfg_lane),
        .cfg_addr(cfg_addr), .cfg_data(cfg_data),
        .i_data(d5), .i_side(s5), .i_valid(v5), .i_ready(r5),
        .o_data(d6), .o_side(s6), .o_valid(v6), .o_ready(r6),
        .st_v(sv6), .st_a(sa6), .st_ch(sc6));
    // 第 7 层 r2d
    conv_layer #(.K(1), .DW(0), .STRIDE(1), .UP(0), .GI(4), .CIN(24), .COUT(24), .G(4), .W(12), .H(8), .PE(1), .R(0), .S(17), .S2(8), .KSK(113384), .SKIP_ADD(1), .FWD(0), .NSTY(6),
        .WFILE(""), .CFILE("")) u_l7 (
        .clk(clk), .rst(rst), .style(style),
        .cfg_we(cfg_we && cfg_layer == 7), .cfg_sel(cfg_sel), .cfg_lane(cfg_lane),
        .cfg_addr(cfg_addr), .cfg_data(cfg_data),
        .i_data(d6), .i_side(s6), .i_valid(v6), .i_ready(r6),
        .o_data(d7), .o_side(s7), .o_valid(v7), .o_ready(r7),
        .st_v(sv7), .st_a(sa7), .st_ch(sc7));
    // 第 8 层 r3a
    conv_layer #(.K(3), .DW(1), .STRIDE(1), .UP(0), .GI(4), .CIN(24), .COUT(24), .G(4), .W(12), .H(8), .PE(1), .R(0), .S(19), .S2(8), .KSK(0), .SKIP_ADD(0), .FWD(1), .NSTY(6),
        .WFILE(""), .CFILE("")) u_l8 (
        .clk(clk), .rst(rst), .style(style),
        .cfg_we(cfg_we && cfg_layer == 8), .cfg_sel(cfg_sel), .cfg_lane(cfg_lane),
        .cfg_addr(cfg_addr), .cfg_data(cfg_data),
        .i_data(d7), .i_side(s7), .i_valid(v7), .i_ready(r7),
        .o_data(d8), .o_side(s8), .o_valid(v8), .o_ready(r8),
        .st_v(sv8), .st_a(sa8), .st_ch(sc8));
    // 第 9 层 r3d
    conv_layer #(.K(1), .DW(0), .STRIDE(1), .UP(0), .GI(4), .CIN(24), .COUT(24), .G(4), .W(12), .H(8), .PE(1), .R(0), .S(18), .S2(8), .KSK(117607), .SKIP_ADD(1), .FWD(0), .NSTY(6),
        .WFILE(""), .CFILE("")) u_l9 (
        .clk(clk), .rst(rst), .style(style),
        .cfg_we(cfg_we && cfg_layer == 9), .cfg_sel(cfg_sel), .cfg_lane(cfg_lane),
        .cfg_addr(cfg_addr), .cfg_data(cfg_data),
        .i_data(d8), .i_side(s8), .i_valid(v8), .i_ready(r8),
        .o_data(d9), .o_side(s9), .o_valid(v9), .o_ready(r9),
        .st_v(sv9), .st_a(sa9), .st_ch(sc9));
    // 第 10 层 d1a
    conv_layer #(.K(3), .DW(1), .STRIDE(1), .UP(1), .GI(4), .CIN(24), .COUT(24), .G(4), .W(12), .H(8), .PE(1), .R(0), .S(20), .S2(8), .KSK(0), .SKIP_ADD(0), .FWD(0), .NSTY(6),
        .WFILE(""), .CFILE("")) u_l10 (
        .clk(clk), .rst(rst), .style(style),
        .cfg_we(cfg_we && cfg_layer == 10), .cfg_sel(cfg_sel), .cfg_lane(cfg_lane),
        .cfg_addr(cfg_addr), .cfg_data(cfg_data),
        .i_data(d9), .i_side(s9), .i_valid(v9), .i_ready(r9),
        .o_data(d10), .o_side(s10), .o_valid(v10), .o_ready(r10),
        .st_v(sv10), .st_a(sa10), .st_ch(sc10));
    // 第 11 层 d1b
    conv_layer #(.K(1), .DW(0), .STRIDE(1), .UP(0), .GI(4), .CIN(24), .COUT(16), .G(4), .W(24), .H(16), .PE(2), .R(0), .S(19), .S2(8), .KSK(0), .SKIP_ADD(0), .FWD(0), .NSTY(6),
        .WFILE(""), .CFILE("")) u_l11 (
        .clk(clk), .rst(rst), .style(style),
        .cfg_we(cfg_we && cfg_layer == 11), .cfg_sel(cfg_sel), .cfg_lane(cfg_lane),
        .cfg_addr(cfg_addr), .cfg_data(cfg_data),
        .i_data(d10), .i_side(s10), .i_valid(v10), .i_ready(r10),
        .o_data(d11), .o_side(s11), .o_valid(v11), .o_ready(r11),
        .st_v(sv11), .st_a(sa11), .st_ch(sc11));
    // 第 12 层 d2
    conv_layer #(.K(3), .DW(0), .STRIDE(1), .UP(0), .GI(4), .CIN(16), .COUT(12), .G(4), .W(24), .H(16), .PE(6), .R(1), .S(22), .S2(8), .KSK(0), .SKIP_ADD(0), .FWD(0), .NSTY(6),
        .WFILE(""), .CFILE("")) u_l12 (
        .clk(clk), .rst(rst), .style(style),
        .cfg_we(cfg_we && cfg_layer == 12), .cfg_sel(cfg_sel), .cfg_lane(cfg_lane),
        .cfg_addr(cfg_addr), .cfg_data(cfg_data),
        .i_data(d11), .i_side(s11), .i_valid(v11), .i_ready(r11),
        .o_data(d12), .o_side(s12), .o_valid(v12), .o_ready(r12),
        .st_v(sv12), .st_a(sa12), .st_ch(sc12));
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
            5'd12: begin tv = sv12; ta = sa12; tc = sc12; end
            default: ;
        endcase
    end
    in_stats #(.CMAX(24)) u_st (.clk(clk), .rst(rst), .arm(st_arm), .frame_start(st_fs),
        .frame_end(st_fe), .i_v(tv), .i_a(ta), .i_ch(tc), .rd_idx(st_idx),
        .rd_s1(st_s1), .rd_s2(st_s2), .done(st_done), .busy(st_busy));
    pixshuf #(.WL(24), .HL(16)) u_ps (
        .clk(clk), .rst(rst), .i_data(d12), .i_valid(v12), .i_ready(r12),
        .o_data(o_data), .o_valid(o_valid), .o_ready(o_ready));
endmodule
