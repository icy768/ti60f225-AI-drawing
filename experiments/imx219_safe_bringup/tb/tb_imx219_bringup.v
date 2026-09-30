`timescale 1ns/1ps
// Compile this file with rtl/imx219_bringup.v ONLY. It replaces the I2C
// transport with a stub to check the register sequence, not the bus waveform.
module i2c_reg16 #(
    parameter integer CLK_HZ=5000000,
    parameter integer I2C_HZ=50000
) (
    input wire clk, rst_n, start, read_not_write,
    input wire [15:0] reg_addr,
    input wire [7:0] write_data,
    input wire scl_i, sda_i,
    output wire scl_drive_low, sda_drive_low,
    output reg [7:0] read_data,
    output reg busy, done, nack
);
    assign scl_drive_low = 1'b0;
    assign sda_drive_low = 1'b0;
    integer write_count = 0;
    integer id_read_count = 0;
    integer stream_on_count = 0;
    integer pattern_count = 0;
    reg pending;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            done <= 0;
            pending <= 0;
            busy <= 0;
            nack <= 0;
            read_data <= 0;
        end else begin
            done <= pending;
            pending <= start;
            busy <= start;
            nack <= 0;
            if (start) begin
                if (read_not_write) begin
                    id_read_count = id_read_count + 1;
                    case (reg_addr)
                        16'h0000: read_data <= 8'h02;
                        16'h0001: read_data <= 8'h19;
                        default: begin
                            read_data <= 8'hff;
                            nack <= 1;
                        end
                    endcase
                end else begin
                    write_count = write_count + 1;
                    if (reg_addr == 16'h0601 && write_data == 8'h02)
                        pattern_count = pattern_count + 1;
                    if (reg_addr == 16'h0100 && write_data == 8'h01)
                        stream_on_count = stream_on_count + 1;
                end
            end
        end
    end
endmodule

module tb_imx219_bringup;
    reg clk = 0;
    always #10 clk = ~clk;
    reg rst_n = 0;
    wire id_ok, done;
    wire [2:0] error_code;
    wire [7:0] config_index;
    wire scl_drive_low, sda_drive_low;
    imx219_bringup #(
        .CLK_HZ(5000000), .I2C_HZ(50000),
        .POWER_WAIT_CYCLES(2), .SENSOR_TEST_PATTERN(1)
    ) dut (
        .clk(clk), .rst_n(rst_n), .enable(1'b1),
        .scl_i(1'b1), .sda_i(1'b1),
        .scl_drive_low(scl_drive_low), .sda_drive_low(sda_drive_low),
        .chip_id_ok(id_ok), .config_done(done),
        .error_code(error_code), .config_index(config_index)
    );
    integer cycles;
    initial begin
        repeat (3) @(posedge clk);
        rst_n = 1;
        for (cycles=0; cycles<600 && !done; cycles=cycles+1)
            @(posedge clk);
        if (!done || !id_ok || error_code != 0 || config_index != 67 ||
            dut.bus.write_count != 67 || dut.bus.id_read_count != 2 ||
            dut.bus.stream_on_count != 1 || dut.bus.pattern_count != 1) begin
            $display("FAIL done=%b id=%b error=%d idx=%d writes=%d reads=%d stream=%d pattern=%d",
                done, id_ok, error_code, config_index,
                dut.bus.write_count, dut.bus.id_read_count,
                dut.bus.stream_on_count, dut.bus.pattern_count);
            $fatal(1);
        end
        $display("PASS: ID probe and 67 ordered register writes, stream-on last");
        $finish;
    end
endmodule
