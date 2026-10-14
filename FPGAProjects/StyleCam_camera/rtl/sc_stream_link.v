// Frame packer for the phone stream: reads RGB565 words from the tap FIFO and writes them to a
// 8N1 serial link as self-delimiting frames.
//
//   offset  bytes  field
//   0       2      sync 0xA5 0x5A
//   1       1      type  0x01 = video frame
//   2       1      seq   frame counter, wraps at 256
//   3       1      width  (pixels)
//   4       1      height (pixels)
//   5       1      format 0 = RGB565 little endian, 1 = RGB332
//   6..7    2      payload length, little endian
//   8..      LEN    payload
//   end     2      CRC16-CCITT (poly 0x1021, init 0xFFFF) over every byte from sync to payload
//
// The receiver resynchronises by scanning for the sync pair, so a frame lost to an aborted
// capture costs one frame and does not desynchronise the stream.
module sc_stream_link #(
 parameter OUT_W = 96,
 parameter OUT_H = 54,
 parameter DIV   = 33,      // clk / baud, 100 MHz clock: 33 -> 3.03 Mbaud
 parameter FMT   = 0        // 0 = RGB565 (2 bytes/pixel), 1 = RGB332 (1 byte/pixel)
)(
 input              clk,
 input              rst,
 output             rready,
 input      [15:0]  rd,
 input              rd_v,
 input              abort_pc,        // toggle in the tap clock domain
 output             uart_tx,
 output reg [31:0]  frames_sent,
 output reg [31:0]  bytes_sent,
 output reg [31:0]  aborts
);
 localparam OUT_W8 = OUT_W[7:0];
 localparam OUT_H8 = OUT_H[7:0];
 localparam BPP    = (FMT == 0) ? 2 : 1;
 localparam LEN    = OUT_W * OUT_H * BPP;
 localparam PW     = $clog2(LEN + 1);
 localparam DRAIN_CYCLES = 3000000;    // ~30 ms: flush a partial frame before restarting

 localparam ST_IDLE    = 3'd0,
            ST_HEADER  = 3'd1,
            ST_PAYLOAD = 3'd2,
            ST_CRC     = 3'd3,
            ST_DRAIN   = 3'd4;

 reg [2:0]    st;
 reg [3:0]    hidx;
 reg [PW-1:0] pidx;
 reg [1:0]    widx;
 reg [15:0]   wbuf;
 reg          whave;
 reg [15:0]   crc;
 reg [1:0]    cidx;
 reg [7:0]    seq;
 reg [21:0]   drain;

 wire tx_ready;
 wire [7:0] rx_data;
 wire rx_valid, rx_error, rx_busy;

 reg [7:0] tx_data;
 reg       tx_valid;

 /* ---- abort toggle synchroniser (tap clock -> link clock) ---- */
 (* async_reg="true" *) reg ab1, ab2;
 reg ab_last;
 always @(posedge clk) begin ab1 <= abort_pc; ab2 <= ab1; ab_last <= ab2; end
 wire ab_edge = ab2 ^ ab_last;

 /* ---- CRC16-CCITT, one byte per step ---- */
 function [15:0] crc_step(input [15:0] c, input [7:0] b);
  integer i;
  reg [15:0] v;
  begin
   v = c ^ {b, 8'h00};
   for (i = 0; i < 8; i = i + 1)
    v = v[15] ? ((v << 1) ^ 16'h1021) : (v << 1);
   crc_step = v;
  end
 endfunction

 /* ---- current payload byte ---- */
 wire [7:0] pay_byte = (FMT == 0) ? (widx == 2'd0 ? wbuf[7:0] : wbuf[15:8]) : wbuf[7:0];

 /* ---- byte currently offered to the UART ---- */
 always @* begin
  tx_valid = 1'b0;
  tx_data  = 8'h00;
  case (st)
   ST_HEADER: begin
    tx_valid = 1'b1;
    case (hidx)
     4'd0: tx_data = 8'hA5;
     4'd1: tx_data = 8'h5A;
     4'd2: tx_data = 8'h01;
     4'd3: tx_data = seq;
     4'd4: tx_data = OUT_W8;
     4'd5: tx_data = OUT_H8;
     4'd6: tx_data = (FMT == 0) ? 8'h00 : 8'h01;
     4'd7: tx_data = LEN[7:0];
     4'd8: tx_data = LEN[15:8];
     default: tx_data = 8'h00;
    endcase
   end
   ST_PAYLOAD: if (whave) begin tx_valid = 1'b1; tx_data = pay_byte; end
   ST_CRC: begin
    tx_valid = 1'b1;
    tx_data  = (cidx == 2'd0) ? crc[7:0] : crc[15:8];
   end
   default: ;
  endcase
 end

 wire emit = tx_valid & tx_ready;                 // byte accepted by the UART this cycle
 assign rready = (st == ST_PAYLOAD) & ~whave & rd_v;

 always @(posedge clk) begin
  if (rst) begin
   st <= ST_IDLE; hidx <= 4'd0; pidx <= 0; widx <= 2'd0; wbuf <= 16'd0; whave <= 1'b0;
   crc <= 16'hFFFF; cidx <= 2'd0; seq <= 8'd0; drain <= 22'd0;
   frames_sent <= 32'd0; bytes_sent <= 32'd0; aborts <= 32'd0;
  end else begin
   if (rready) begin wbuf <= rd; whave <= 1'b1; widx <= 2'd0; end

   if (emit) begin
    bytes_sent <= bytes_sent + 1'b1;
    if (st == ST_HEADER) begin
     crc <= crc_step(crc, tx_data);
     if (hidx == 4'd8) begin st <= ST_PAYLOAD; hidx <= 4'd0; pidx <= 0; end
     else               hidx <= hidx + 1'b1;
    end else if (st == ST_PAYLOAD) begin
     crc  <= crc_step(crc, tx_data);
     pidx <= pidx + 1'b1;
     if ((FMT == 0 && widx == 2'd1) || (FMT == 1 && widx == 2'd0)) begin
      whave <= 1'b0;
      widx  <= 2'd0;
     end else begin
      widx <= widx + 1'b1;
     end
     if (pidx == LEN - 1) begin st <= ST_CRC; cidx <= 2'd0; end
    end else if (st == ST_CRC) begin
     if (cidx == 2'd1) begin
      st <= ST_IDLE;
      seq <= seq + 1'b1;
      crc <= 16'hFFFF;
      frames_sent <= frames_sent + 1'b1;
     end else begin
      cidx <= cidx + 1'b1;
     end
    end
   end

   /* ---- state entry ---- */
   if (st == ST_IDLE && rd_v) begin
    st <= ST_HEADER; hidx <= 4'd0; pidx <= 0; widx <= 2'd0; whave <= 1'b0; crc <= 16'hFFFF;
   end

   /* ---- abandoned capture: flush the partial frame and restart cleanly ---- */
   if (ab_edge && (st != ST_IDLE) && (st != ST_DRAIN)) begin
    st <= ST_DRAIN;
    drain <= DRAIN_CYCLES;
    aborts <= aborts + 1'b1;
   end

   if (st == ST_DRAIN) begin
    if (drain != 0) drain <= drain - 1'b1;
    else            st <= ST_IDLE;
   end
  end
 end

 uart_byte #(.DIV(DIV)) uart(
  .clk(clk), .rst(rst), .rx(1'b1), .tx(uart_tx),
  .rx_data(rx_data), .rx_valid(rx_valid), .rx_error(rx_error),
  .tx_data(tx_data), .tx_valid(tx_valid), .tx_ready(tx_ready), .rx_busy(rx_busy));
endmodule
