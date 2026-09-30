// IMX219 control-plane bring-up only. This is not a CSI/HDMI design.
// It probes chip ID 0x0219, then selects 1920x1080 RAW10, two CSI lanes.
// Assumes the module is already correctly powered, released from reset,
// and supplied with a verified 24 MHz sensor reference clock.
module imx219_bringup #(
    parameter integer CLK_HZ = 5000000,
    parameter integer I2C_HZ = 50000,
    parameter integer POWER_WAIT_CYCLES = CLK_HZ / 100,
    parameter integer SENSOR_TEST_PATTERN = 1
) (
    input  wire clk,
    input  wire rst_n,
    input  wire enable,
    input  wire scl_i,
    input  wire sda_i,
    output wire scl_drive_low,
    output wire sda_drive_low,
    output reg  chip_id_ok,
    output reg  config_done,
    output reg  [2:0] error_code,
    output reg  [7:0] config_index
);
    localparam [2:0] NO_ERROR=0, ID_NACK=1, WRONG_ID=2, CONFIG_NACK=3;
    localparam [3:0] WAIT_POWER=0, ID0_REQ=1, ID0_WAIT=2,
                     ID1_REQ=3, ID1_WAIT=4, CFG_REQ=5,
                     CFG_WAIT=6, FINISHED=7, FAILED=8;
    reg [3:0] state;
    reg [31:0] wait_count;
    reg i2c_start;
    reg i2c_read;
    reg [15:0] i2c_reg;
    reg [7:0] i2c_data;
    wire [7:0] i2c_result;
    wire i2c_busy, i2c_done, i2c_nack;

    i2c_reg16 #(.CLK_HZ(CLK_HZ), .I2C_HZ(I2C_HZ)) bus (
        .clk(clk), .rst_n(rst_n && enable),
        .start(i2c_start), .read_not_write(i2c_read),
        .reg_addr(i2c_reg), .write_data(i2c_data),
        .scl_i(scl_i), .sda_i(sda_i),
        .scl_drive_low(scl_drive_low), .sda_drive_low(sda_drive_low),
        .read_data(i2c_result), .busy(i2c_busy),
        .done(i2c_done), .nack(i2c_nack)
    );

    function [23:0] setting;
        input [7:0] idx;
        begin
            // Address[23:8], value[7:0]. Sequence based on the upstream
            // Linux IMX219 driver; dynamic crop/timing values are for a
            // centered 1920x1080, RAW10, two-lane, 24 MHz XCLK mode.
            case (idx)
              8'd0: setting={16'h0100,8'h00};
              8'd1: setting={16'h30eb,8'h05};
              8'd2: setting={16'h30eb,8'h0c};
              8'd3: setting={16'h300a,8'hff};
              8'd4: setting={16'h300b,8'hff};
              8'd5: setting={16'h30eb,8'h05};
              8'd6: setting={16'h30eb,8'h09};
              8'd7: setting={16'h455e,8'h00};
              8'd8: setting={16'h471e,8'h4b};
              8'd9: setting={16'h4767,8'h0f};
              8'd10: setting={16'h4750,8'h14};
              8'd11: setting={16'h4540,8'h00};
              8'd12: setting={16'h47b4,8'h14};
              8'd13: setting={16'h4713,8'h30};
              8'd14: setting={16'h478b,8'h10};
              8'd15: setting={16'h478f,8'h10};
              8'd16: setting={16'h4793,8'h10};
              8'd17: setting={16'h4797,8'h0e};
              8'd18: setting={16'h479b,8'h0e};
              8'd19: setting={16'h0170,8'h01};
              8'd20: setting={16'h0171,8'h01};
              8'd21: setting={16'h0128,8'h00};
              8'd22: setting={16'h012a,8'h18};
              8'd23: setting={16'h012b,8'h00};
              8'd24: setting={16'h0301,8'h05};
              8'd25: setting={16'h0303,8'h01};
              8'd26: setting={16'h0304,8'h03};
              8'd27: setting={16'h0305,8'h03};
              8'd28: setting={16'h0306,8'h00};
              8'd29: setting={16'h0307,8'h39};
              8'd30: setting={16'h030b,8'h01};
              8'd31: setting={16'h030c,8'h00};
              8'd32: setting={16'h030d,8'h72};
              8'd33: setting={16'h0114,8'h01};
              8'd34: setting={16'h0164,8'h02}; // crop X start 0x02a8
              8'd35: setting={16'h0165,8'ha8};
              8'd36: setting={16'h0166,8'h0a}; // crop X end 0x0a27
              8'd37: setting={16'h0167,8'h27};
              8'd38: setting={16'h0168,8'h02}; // crop Y start 0x02b4
              8'd39: setting={16'h0169,8'hb4};
              8'd40: setting={16'h016a,8'h06}; // crop Y end 0x06eb
              8'd41: setting={16'h016b,8'heb};
              8'd42: setting={16'h0174,8'h00}; // no binning
              8'd43: setting={16'h0175,8'h00};
              8'd44: setting={16'h016c,8'h07}; // output 1920
              8'd45: setting={16'h016d,8'h80};
              8'd46: setting={16'h016e,8'h04}; // output 1080
              8'd47: setting={16'h016f,8'h38};
              8'd48: setting={16'h0624,8'h07};
              8'd49: setting={16'h0625,8'h80};
              8'd50: setting={16'h0626,8'h04};
              8'd51: setting={16'h0627,8'h38};
              8'd52: setting={16'h018c,8'h0a}; // RAW10
              8'd53: setting={16'h018d,8'h0a};
              8'd54: setting={16'h0309,8'h0a};
              8'd55: setting={16'h0160,8'h06}; // frame length 1763
              8'd56: setting={16'h0161,8'he3};
              8'd57: setting={16'h0162,8'h0d}; // line length 3448
              8'd58: setting={16'h0163,8'h78};
              8'd59: setting={16'h015a,8'h06}; // exposure 1600 lines
              8'd60: setting={16'h015b,8'h40};
              8'd61: setting={16'h0157,8'h00};
              8'd62: setting={16'h0158,8'h01};
              8'd63: setting={16'h0159,8'h00};
              8'd64: setting={16'h0600,8'h00};
              8'd65: setting={16'h0601,SENSOR_TEST_PATTERN ? 8'h02 : 8'h00};
              8'd66: setting={16'h0100,8'h01}; // stream on last
              default: setting={16'hffff,8'h00};
            endcase
        end
    endfunction

    wire [23:0] next_setting = setting(config_index);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= WAIT_POWER;
            wait_count <= 0;
            i2c_start <= 0;
            i2c_read <= 0;
            i2c_reg <= 0;
            i2c_data <= 0;
            chip_id_ok <= 0;
            config_done <= 0;
            error_code <= NO_ERROR;
            config_index <= 0;
        end else if (!enable) begin
            state <= WAIT_POWER;
            wait_count <= 0;
            i2c_start <= 0;
            chip_id_ok <= 0;
            config_done <= 0;
            error_code <= NO_ERROR;
            config_index <= 0;
        end else begin
            i2c_start <= 0;
            case (state)
                WAIT_POWER: begin
                    if (wait_count >= POWER_WAIT_CYCLES-1)
                        state <= ID0_REQ;
                    else wait_count <= wait_count + 1'b1;
                end
                ID0_REQ: begin
                    i2c_reg <= 16'h0000;
                    i2c_read <= 1'b1;
                    i2c_start <= 1'b1;
                    state <= ID0_WAIT;
                end
                ID0_WAIT: if (i2c_done) begin
                    if (i2c_nack) begin
                        error_code <= ID_NACK;
                        state <= FAILED;
                    end else if (i2c_result != 8'h02) begin
                        error_code <= WRONG_ID;
                        state <= FAILED;
                    end else state <= ID1_REQ;
                end
                ID1_REQ: begin
                    i2c_reg <= 16'h0001;
                    i2c_read <= 1'b1;
                    i2c_start <= 1'b1;
                    state <= ID1_WAIT;
                end
                ID1_WAIT: if (i2c_done) begin
                    if (i2c_nack) begin
                        error_code <= ID_NACK;
                        state <= FAILED;
                    end else if (i2c_result != 8'h19) begin
                        error_code <= WRONG_ID;
                        state <= FAILED;
                    end else begin
                        chip_id_ok <= 1'b1;
                        state <= CFG_REQ;
                    end
                end
                CFG_REQ: begin
                    if (next_setting[23:8] == 16'hffff) begin
                        config_done <= 1'b1;
                        state <= FINISHED;
                    end else begin
                        i2c_reg <= next_setting[23:8];
                        i2c_data <= next_setting[7:0];
                        i2c_read <= 1'b0;
                        i2c_start <= 1'b1;
                        state <= CFG_WAIT;
                    end
                end
                CFG_WAIT: if (i2c_done) begin
                    if (i2c_nack) begin
                        error_code <= CONFIG_NACK;
                        state <= FAILED;
                    end else begin
                        config_index <= config_index + 1'b1;
                        state <= CFG_REQ;
                    end
                end
                FINISHED: state <= FINISHED;
                FAILED: state <= FAILED;
                default: state <= FAILED;
            endcase
        end
    end
endmodule
