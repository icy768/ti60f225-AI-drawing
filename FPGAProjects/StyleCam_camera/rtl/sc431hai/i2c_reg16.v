// Open-drain 7-bit 0x30 I2C register access: 16-bit address, 8-bit data.
module i2c_reg16 #(
    parameter integer TICK_CYCLES = 250, // 10 us at 25 MHz
    parameter integer TIMEOUT_TICKS = 1000
)(
    input wire clk, reset, scl_in, sda_in, start, read_op,
    input wire [15:0] reg_addr,
    input wire [7:0] write_data,
    output reg scl_low, sda_low, busy, done,
    output reg [2:0] result, // 1 OK, 2 NACK, 4 timeout
    output reg [7:0] read_data
);
    localparam IDLE=0, BUS_FREE=1, START=2, START_LOW=3,
               TRANSFER=4, RESTART_LOW=5, RESTART_RISE=6,
               RESTART_WAIT=7, RESTART_HOLD=8,
               STOP_LOW=9, STOP_RISE=10, STOP_WAIT=11,
               STOP_RELEASE=12, STOP_CHECK=13, FINISH=14, RESTART_FALL=15;
    reg read_latched;
    reg [15:0] addr_latched;
    reg [7:0] data_latched;
    reg [3:0] state;
    reg [1:0] phase;
    reg [3:0] bit_index;
    reg [2:0] byte_index; // 20, addr HI, addr LO, data or 21, read byte
    reg [7:0] tx_byte, rx_byte;
    reg [31:0] divider, wait_ticks;
    (* async_reg = "true" *) reg [1:0] scl_sync, sda_sync;
    wire scl = scl_sync[1];
    wire sda = sda_sync[1];
    always @(posedge clk) begin
        if (reset) begin
            scl_sync <= 2'b11; sda_sync <= 2'b11;
        end else begin
            scl_sync <= {scl_sync[0],scl_in};
            sda_sync <= {sda_sync[0],sda_in};
        end
    end
    // A wait state increments this bounded watchdog. Any timeout releases both pads.
    task wait_or_abort;
        begin
            if (wait_ticks == TIMEOUT_TICKS-1) begin
                scl_low <= 0; sda_low <= 0;
                result <= 4; state <= FINISH;
            end else wait_ticks <= wait_ticks+1;
        end
    endtask
    always @(posedge clk) begin
        if (reset) begin
            state<=IDLE; phase<=0; bit_index<=0; byte_index<=0;
            tx_byte<=0; rx_byte<=0; divider<=0; wait_ticks<=0;
            scl_low<=0; sda_low<=0; busy<=0;
            result<=0; done<=0; read_data<=0;
            read_latched<=0; addr_latched<=0; data_latched<=0;
        end else if (state==IDLE) begin
            divider<=0; done<=0;
            if(start) begin
                busy<=1; result<=0; read_data<=0;
                read_latched<=read_op; addr_latched<=reg_addr; data_latched<=write_data;
                wait_ticks<=0; state<=BUS_FREE;
            end
        end else if (state==FINISH) begin
            scl_low<=0; sda_low<=0; busy<=0; done<=1; state<=IDLE;
        end else if (divider != TICK_CYCLES-1) divider<=divider+1;
        else begin
            divider<=0;
            case (state)
                BUS_FREE: begin
                    if (scl && sda) begin state<=START; wait_ticks<=0; end
                    else wait_or_abort;
                end
                START: begin
                    if (scl && sda) begin sda_low<=1; state<=START_LOW; end
                    else begin state<=BUS_FREE; end
                end
                START_LOW: begin
                    scl_low<=1; state<=TRANSFER; phase<=0;
                    bit_index<=0; byte_index<=0; tx_byte<=8'h60;
                end
                TRANSFER: case (phase)
                    0: begin
                        // SCL has already been low for a tick before SDA changes.
                        scl_low<=1;
                        if (byte_index<4)
                            sda_low <= (bit_index<8) ? ~tx_byte[7-bit_index] : 1'b0;
                        else
                            sda_low <= 0; // Single-byte read always ends with master NACK
                        phase<=1;
                    end
                    1: begin scl_low<=0; wait_ticks<=0; phase<=2; end
                    2: begin
                        if (scl) begin phase<=3; wait_ticks<=0; end
                        else wait_or_abort;
                    end
                    3: begin
                        if (!scl) wait_or_abort;
                        else begin
                            scl_low<=1; phase<=0; wait_ticks<=0;
                            if (bit_index<8) begin
                                if (byte_index>=4) rx_byte<={rx_byte[6:0],sda};
                                bit_index<=bit_index+4'd1;
                            end else begin
                                bit_index<=0;
                                if (byte_index<4 && sda) begin
                                    result<=2; state<=STOP_LOW;
                                end else begin
                                    case (byte_index)
                                        0: begin byte_index<=1; tx_byte<=addr_latched[15:8]; end
                                        1: begin byte_index<=2; tx_byte<=addr_latched[7:0]; end
                                        2: begin
                                            byte_index<=3;
                                            if(read_latched) begin tx_byte<=8'h61; state<=RESTART_LOW; end
                                            else tx_byte<=data_latched;
                                        end
                                        3: begin
                                            if(read_latched) begin byte_index<=4; rx_byte<=0; end
                                            else state<=STOP_LOW;
                                        end
                                        4: begin read_data<=rx_byte; state<=STOP_LOW; end
                                        default: begin result<=4; state<=STOP_LOW; end
                                    endcase
                                end
                            end
                        end
                    end
                endcase
                RESTART_LOW: begin sda_low<=0; state<=RESTART_RISE; end
                RESTART_RISE: begin scl_low<=0; wait_ticks<=0; state<=RESTART_WAIT; end
                RESTART_WAIT: begin
                    if (scl && sda) begin wait_ticks<=0; state<=RESTART_HOLD; end
                    else wait_or_abort;
                end
                RESTART_HOLD: begin
                    // SDA falls while SCL stays high for a full tick.
                    sda_low<=1; state<=RESTART_FALL;
                end
                RESTART_FALL: begin
                    scl_low<=1; state<=TRANSFER; phase<=0;
                end
                STOP_LOW: begin scl_low<=1; sda_low<=1; state<=STOP_RISE; end
                STOP_RISE: begin scl_low<=0; wait_ticks<=0; state<=STOP_WAIT; end
                STOP_WAIT: begin
                    if (scl) begin state<=STOP_RELEASE; wait_ticks<=0; end
                    else wait_or_abort;
                end
                STOP_RELEASE: begin sda_low<=0; state<=STOP_CHECK; end
                STOP_CHECK: begin
                    if (scl && sda) begin
                        if (result==0) result <= 1;
                        state<=FINISH;
                    end else wait_or_abort;
                end
                default: begin result<=4; scl_low<=0; sda_low<=0; state<=FINISH; end
            endcase
        end
    end
endmodule
