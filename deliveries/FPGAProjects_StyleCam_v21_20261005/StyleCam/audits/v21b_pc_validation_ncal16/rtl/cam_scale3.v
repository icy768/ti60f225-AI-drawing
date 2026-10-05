// 摄像头预处理：水平裁剪 + 3x3 盒式均值降采样（每拍输入 2 像素）
//   默认 2560x1440 → 裁中间 1920x1440（4:3）→ 640x480
//   水平：每 3 个像素求和（以 6 像素 / 3 拍为周期，第 2、3 拍各出 1 个和）
//   垂直：行缓存累加 3 行，第 3 行时 /9 输出（(s*7282+32768)>>16，对 0..2295 与整除一致到 ±0.5）
// 输入不可反压（摄像头实时流）；输出每拍至多 1 像素
module cam_scale3 #(
    parameter IW   = 2560,
    parameter IH   = 1440,
    parameter XOFF = 320,     // 偶数
    parameter CW   = 1920     // 6 的倍数
)(
    input               clk,
    input               rst,
    input               i_valid,
    input               i_sof,     // 帧首像素标志
    input  [47:0]       i_data,    // {p1, p0}，每像素 {B,G,R}，R 在低字节
    output reg          o_valid,
    output reg          o_sof,
    output reg [23:0]   o_data
);
    localparam OW = CW / 3;
    localparam XAW = $clog2(OW);

    reg [15:0] x, y;           // 当前输入字的像素坐标（x 为 p0 的列）
    reg [1:0]  ph, rv;         // 水平相位、行相位
    reg [9:0]  ar, ag, ab;     // 水平部分和
    wire [23:0] p0 = i_data[23:0], p1 = i_data[47:24];

    // 水平求和输出
    reg        h_v, h_sof;
    reg [11:0] h_r, h_g, h_b;
    reg [XAW-1:0] h_x;
    reg [1:0]  h_rv;

    wire [15:0] xi = i_sof ? 16'd0 : x;
    wire [15:0] yi = i_sof ? 16'd0 : y;
    wire [1:0]  ri = i_sof ? 2'd0 : rv;
    reg  [XAW-1:0] hx;         // 下一个水平和的输出列

    always @(posedge clk) begin
        if (rst) begin
            x <= 0; y <= 0; ph <= 0; rv <= 0; h_v <= 0;
        end else begin
            h_v <= 1'b0;
            if (i_valid) begin
                // 坐标推进（i_sof 强制归零）
                if (xi + 2 >= IW) begin
                    x  <= 0;
                    y  <= yi + 1;
                    rv <= (ri == 2) ? 2'd0 : ri + 1'b1;
                end else begin
                    x  <= xi + 2;
                    y  <= yi;
                    rv <= ri;
                end
                if ((xi >= XOFF) && (xi < XOFF + CW)) begin
                    case ((xi == XOFF) ? 2'd0 : ph)
                        2'd0: begin
                            ar <= p0[7:0] + p1[7:0];
                            ag <= p0[15:8] + p1[15:8];
                            ab <= p0[23:16] + p1[23:16];
                            ph <= 2'd1;
                        end
                        2'd1: begin
                            h_r <= ar + p0[7:0];
                            h_g <= ag + p0[15:8];
                            h_b <= ab + p0[23:16];
                            ar <= p1[7:0];
                            ag <= p1[15:8];
                            ab <= p1[23:16];
                            h_v <= 1'b1;
                            ph <= 2'd2;
                        end
                        default: begin
                            h_r <= ar + p0[7:0] + p1[7:0];
                            h_g <= ag + p0[15:8] + p1[15:8];
                            h_b <= ab + p0[23:16] + p1[23:16];
                            h_v <= 1'b1;
                            ph <= 2'd0;
                        end
                    endcase
                    // 输出列计数：裁剪区首字清零，每出一个水平和加一
                    if (xi == XOFF) hx <= 0;
                    else if (ph != 0) hx <= hx + 1'b1;
                    h_x   <= (xi == XOFF) ? {XAW{1'b0}} : hx;
                    h_rv  <= ri;
                    h_sof <= (yi == 2) && (xi == XOFF + 2);
                end
            end
        end
    end

    // 垂直累加：行缓存读-改-写
    wire [35:0] lb_q;
    reg         v_v, v_sof;
    reg [1:0]   v_rv;
    reg [XAW-1:0] v_x;
    reg [11:0]  v_r, v_g, v_b;
    wire [11:0] q_r = lb_q[11:0], q_g = lb_q[23:12], q_b = lb_q[35:24];
    wire [11:0] s_r = (v_rv == 0) ? v_r : q_r + v_r;
    wire [11:0] s_g = (v_rv == 0) ? v_g : q_g + v_g;
    wire [11:0] s_b = (v_rv == 0) ? v_b : q_b + v_b;

    sdpram #(.W(36), .D(OW), .AW(XAW)) u_lb (
        .clk(clk), .we(v_v && v_rv != 2), .waddr(v_x), .wdata({s_b, s_g, s_r}),
        .re(h_v), .raddr(h_x), .rdata(lb_q)
    );

    function [7:0] div9(input [11:0] s);
        reg [27:0] t;
        begin
            t = s * 14'd7282 + 28'd32768;
            div9 = t[23:16];
        end
    endfunction

    always @(posedge clk) begin
        if (rst) begin
            v_v <= 0; o_valid <= 0;
        end else begin
            v_v   <= h_v;
            v_x   <= h_x;
            v_rv  <= h_rv;
            v_sof <= h_sof;
            v_r <= h_r; v_g <= h_g; v_b <= h_b;
            o_valid <= v_v && (v_rv == 2);
            o_sof   <= v_sof && (v_rv == 2) && (v_x == 0);
            o_data  <= {div9(s_b), div9(s_g), div9(s_r)};
        end
    end
endmodule
