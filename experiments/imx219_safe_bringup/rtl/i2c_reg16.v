// Minimal open-drain I2C master for one IMX219 register transaction.
// A transaction is either: START, 0x20, reg_hi, reg_lo, data, STOP
// or: START, 0x20, reg_hi, reg_lo, RESTART, 0x21, byte, NACK, STOP.
// The caller must supply pull-ups and an electrically compatible camera.
module i2c_reg16 #(
    parameter integer CLK_HZ = 5000000,
    parameter integer I2C_HZ = 50000,
    parameter integer SCL_TIMEOUT_CYCLES = CLK_HZ / 100
) (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       start,
    input  wire       read_not_write,
    input  wire [15:0] reg_addr,
    input  wire [7:0] write_data,
    input  wire       scl_i,
    input  wire       sda_i,
    output reg        scl_drive_low,
    output reg        sda_drive_low,
    output reg  [7:0] read_data,
    output reg        busy,
    output reg        done,
    output reg        nack
);
    localparam integer DIVIDER = (CLK_HZ / (I2C_HZ * 4) < 2)
                                 ? 2 : CLK_HZ / (I2C_HZ * 4);
    localparam integer DIV_WIDTH = $clog2(DIVIDER);
    reg [DIV_WIDTH-1:0] div_count;
    wire tick = (div_count == DIVIDER-1);
    reg [31:0] high_wait_count;

    localparam [4:0]
        IDLE=0, START_A=1, START_B=2,
        TX_LOW=3, TX_HOLD=4, TX_HIGH=5, TX_SAMPLE=6,
        ACK_LOW=7, ACK_HOLD=8, ACK_HIGH=9, ACK_SAMPLE=10,
        RESTART_LOW=11, RESTART_HIGH=12, RESTART_FALL=13,
        RX_LOW=14, RX_HOLD=15, RX_HIGH=16, RX_SAMPLE=17,
        NACK_LOW=18, NACK_HIGH=19,
        STOP_LOW=20, STOP_HIGH=21, STOP_RELEASE=22;

    reg [4:0] state;
    reg [2:0] bit_index;
    reg [2:0] byte_index;
    reg [15:0] saved_addr;
    reg [7:0] saved_data;
    reg saved_read;
    reg [7:0] tx_byte;

    always @* begin
        case (byte_index)
            3'd0: tx_byte = 8'h20; // 7-bit address 0x10, write
            3'd1: tx_byte = saved_addr[15:8];
            3'd2: tx_byte = saved_addr[7:0];
            3'd3: tx_byte = saved_read ? 8'h21 : saved_data;
            default: tx_byte = 8'hff;
        endcase
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            div_count <= 0;
        end else if (state == IDLE || tick) begin
            div_count <= 0;
        end else begin
            div_count <= div_count + 1'b1;
        end
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) high_wait_count <= 0;
        else if (!busy || scl_drive_low || scl_i) high_wait_count <= 0;
        else if (high_wait_count < SCL_TIMEOUT_CYCLES)
            high_wait_count <= high_wait_count + 1'b1;
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= IDLE;
            scl_drive_low <= 1'b0;
            sda_drive_low <= 1'b0;
            read_data <= 0;
            busy <= 1'b0;
            done <= 1'b0;
            nack <= 1'b0;
            bit_index <= 0;
            byte_index <= 0;
            saved_addr <= 0;
            saved_data <= 0;
            saved_read <= 0;
        end else begin
            done <= 1'b0;
            if (high_wait_count >= SCL_TIMEOUT_CYCLES) begin
                // A low SCL despite being released suggests a wiring fault
                // or excessive clock stretch; leave both lines released.
                scl_drive_low <= 1'b0;
                sda_drive_low <= 1'b0;
                busy <= 1'b0;
                done <= 1'b1;
                nack <= 1'b1;
                state <= IDLE;
            end else if (state == IDLE) begin
                if (start) begin
                    saved_addr <= reg_addr;
                    saved_data <= write_data;
                    saved_read <= read_not_write;
                    byte_index <= 0;
                    bit_index <= 7;
                    read_data <= 0;
                    nack <= 1'b0;
                    busy <= 1'b1;
                    scl_drive_low <= 1'b0;
                    sda_drive_low <= 1'b0;
                    state <= START_A;
                end
            end else if (tick) begin
                case (state)
                    START_A: begin
                        // Bus idle high before START.
                        scl_drive_low <= 1'b0;
                        sda_drive_low <= 1'b0;
                        if (scl_i) state <= START_B;
                    end
                    START_B: begin
                        sda_drive_low <= 1'b1;
                        state <= TX_LOW;
                    end
                    TX_LOW: begin
                        scl_drive_low <= 1'b1;
                        state <= TX_HOLD;
                    end
                    TX_HOLD: begin
                        sda_drive_low <= ~tx_byte[bit_index];
                        state <= TX_HIGH;
                    end
                    TX_HIGH: begin
                        scl_drive_low <= 1'b0;
                        state <= TX_SAMPLE;
                    end
                    TX_SAMPLE: if (scl_i) begin
                        if (bit_index == 0) state <= ACK_LOW;
                        else begin
                            bit_index <= bit_index - 1'b1;
                            state <= TX_LOW;
                        end
                    end
                    ACK_LOW: begin
                        scl_drive_low <= 1'b1;
                        sda_drive_low <= 1'b0;
                        state <= ACK_HOLD;
                    end
                    ACK_HOLD: state <= ACK_HIGH;
                    ACK_HIGH: begin
                        scl_drive_low <= 1'b0;
                        state <= ACK_SAMPLE;
                    end
                    ACK_SAMPLE: if (scl_i) begin
                        if (sda_i) begin
                            nack <= 1'b1;
                            state <= STOP_LOW;
                        end else if (byte_index == 3) begin
                            if (saved_read) begin
                                bit_index <= 7;
                                state <= RX_LOW;
                            end else state <= STOP_LOW;
                        end else if (saved_read && byte_index == 2) begin
                            byte_index <= 3;
                            bit_index <= 7;
                            state <= RESTART_LOW;
                        end else begin
                            byte_index <= byte_index + 1'b1;
                            bit_index <= 7;
                            state <= TX_LOW;
                        end
                    end
                    RESTART_LOW: begin
                        scl_drive_low <= 1'b1;
                        sda_drive_low <= 1'b0;
                        state <= RESTART_HIGH;
                    end
                    RESTART_HIGH: begin
                        scl_drive_low <= 1'b0;
                        if (scl_i) state <= RESTART_FALL;
                    end
                    RESTART_FALL: begin
                        sda_drive_low <= 1'b1;
                        state <= TX_LOW;
                    end
                    RX_LOW: begin
                        scl_drive_low <= 1'b1;
                        sda_drive_low <= 1'b0;
                        state <= RX_HOLD;
                    end
                    RX_HOLD: state <= RX_HIGH;
                    RX_HIGH: begin
                        scl_drive_low <= 1'b0;
                        state <= RX_SAMPLE;
                    end
                    RX_SAMPLE: if (scl_i) begin
                        read_data[bit_index] <= sda_i;
                        if (bit_index == 0) state <= NACK_LOW;
                        else begin
                            bit_index <= bit_index - 1'b1;
                            state <= RX_LOW;
                        end
                    end
                    NACK_LOW: begin
                        scl_drive_low <= 1'b1;
                        sda_drive_low <= 1'b0; // Master sends NACK (release SDA).
                        state <= NACK_HIGH;
                    end
                    NACK_HIGH: begin
                        scl_drive_low <= 1'b0;
                        if (scl_i) state <= STOP_LOW;
                    end
                    STOP_LOW: begin
                        scl_drive_low <= 1'b1;
                        sda_drive_low <= 1'b1;
                        state <= STOP_HIGH;
                    end
                    STOP_HIGH: begin
                        scl_drive_low <= 1'b0;
                        if (scl_i) state <= STOP_RELEASE;
                    end
                    STOP_RELEASE: begin
                        sda_drive_low <= 1'b0;
                        busy <= 1'b0;
                        done <= 1'b1;
                        state <= IDLE;
                    end
                    default: state <= IDLE;
                endcase
            end
        end
    end
endmodule
