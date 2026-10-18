// Self-checking testbench for the phone preview tap and frame packer.
//
// A synthetic display raster (de + 24-bit colour) is decimated by sc_stream_tap, handed to
// sc_stream_link through the same asynchronous FIFO the board uses, and the serial output is
// decoded again.  The bench checks the header, the CRC16 and every one of the OUT_W*OUT_H
// pixels against the value the raster should have produced at that grid position.
//
// The raster here is deliberately small (160x120 shown as 40x30) and the link divisor is short
// so the whole run fits in a few hundred microseconds of simulated time; the module parameters
// used on the board are 1920x1080 / SX=SY=20 / DIV=33.
`timescale 1ns / 1ps

module stream_link_tb #(parameter FULL_SIZE=0, RECOVERY=0, FMT=0,
 parameter real PIX_SCALE=1.0);
 localparam SRC_W = FULL_SIZE ? 1920 : (RECOVERY ? 32 : 160);
 localparam SRC_H = FULL_SIZE ? 1080 : (RECOVERY ? 16 : 120);
 localparam SX = FULL_SIZE ? 20 : (RECOVERY ? 2 : 4), SY = SX;
 localparam OUT_W = SRC_W / SX;      // 40
 localparam OUT_H = SRC_H / SY;      // 30
 localparam NPIX  = OUT_W * OUT_H;   // 1200
 localparam BPP = FMT == 0 ? 2 : 1;
 localparam LEN = NPIX * BPP;
 localparam LINE = FULL_SIZE ? 2200 : (RECOVERY ? 40 : 200);
 localparam FRAME_LINES = FULL_SIZE ? 1125 : (RECOVERY ? 20 : 150);
 localparam DIV = FULL_SIZE ? 33 : 4;
 localparam AW = RECOVERY ? 6 : (FMT == 1 ? 10 : 12);
 localparam PACE = (FMT == 1 || RECOVERY) ? 0 : (FULL_SIZE ? 1024 : 600);
 localparam real PIX_HALF = (FULL_SIZE ? 3.367 : (RECOVERY ? 100.0 : 5.0))*PIX_SCALE;
 localparam real CORE_HALF = FULL_SIZE ? 5.0 : (RECOVERY ? 1.0 : 3.0);

 reg pc = 1'b0, prst = 1'b1;
 reg clk = 1'b0, rst = 1'b1;
 reg [15:0] x = 0, y = 0;

 always #(PIX_HALF) pc = ~pc;
 always #(CORE_HALF) clk = ~clk;

 always @(posedge pc) begin
  if (x == LINE - 1) begin x <= 0; y <= (y == FRAME_LINES - 1) ? 0 : y + 1; end
  else x <= x + 1;
 end

 wire de = (x < SRC_W) && (y < SRC_H);
 wire vs = (y >= SRC_H) && (y < SRC_H + 6);      // field pulse, as in sc_display
 wire [7:0] red   = x[7:0];
 wire [7:0] green = y[7:0];
 wire [7:0] blue  = (x + y) & 8'hFF;

 /* ---------------- device under test ---------------- */
 wire [15:0] wd; wire wv, wready, abort_toggle;
 wire [31:0] tap_frames, tap_drops;
 wire [12:0] wlevel;
 wire [AW:0] fifo_level;
 assign wlevel = fifo_level;
 wire [BPP*8-1:0] rd; wire rd_v, rready;
 wire stream_tx, flush_capture;
 wire [31:0] link_frames, link_bytes, link_aborts;

 sc_stream_tap #(.SRC_W(SRC_W), .SRC_H(SRC_H), .SX(SX), .SY(SY), .PACE_WORDS(PACE), .FMT(FMT)) tap(
  .pc(pc), .prst(prst), .de(de), .vs(vs), .red(red), .green(green), .blue(blue),
  .wready(wready), .flush_capture(flush_capture), .wlevel(wlevel), .wd(wd), .wv(wv),
  .abort_toggle(abort_toggle), .tap_frames(tap_frames), .tap_drops(tap_drops));

 sc_async_fifo #(.W(BPP*8), .AW(AW)) fifo(
  .wc(pc), .wrst(prst), .wd(wd[BPP*8-1:0]), .wv(wv), .wready(wready), .wlevel(fifo_level),
  .rc(clk), .rrst(rst), .rd(rd), .rv(rd_v), .rready(rready));

 wire [15:0] link_word=rd;
 sc_stream_link #(.OUT_W(OUT_W), .OUT_H(OUT_H), .DIV(DIV), .FMT(FMT), .DRAIN_CYCLES(RECOVERY ? 1000 : 3000000)) link(
  .clk(clk), .rst(rst), .rready(rready), .rd(link_word), .rd_v(rd_v), .abort_pc(abort_toggle),
  .uart_tx(stream_tx), .flush_capture(flush_capture), .frames_sent(link_frames), .bytes_sent(link_bytes), .aborts(link_aborts));

 /* ---------------- serial receiver ---------------- */
 wire [7:0] rx_data; wire rx_valid, rx_error, rx_busy;
 uart_byte #(.DIV(DIV)) rx(
  .clk(clk), .rst(rst), .rx(stream_tx), .tx(),
  .rx_data(rx_data), .rx_valid(rx_valid), .rx_error(rx_error),
  .tx_data(8'h00), .tx_valid(1'b0), .tx_ready(), .rx_busy(rx_busy));

 /* ---------------- frame decoder and checker ---------------- */
 integer sync_state = 0;
 integer n = 0;
 integer len = 0;
 integer good = 0, bad = 0, pix_bad = 0;
 reg [7:0] frm [0:LEN+16];
 reg [15:0] crc;
 reg [15:0] crc_lo_hi;

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

 integer i, j, k;
 reg [15:0] got, exp;
 reg [7:0] r8, g8, b8;

 always @(posedge clk) begin
  if (!rst && rx_valid) begin
   if (rx_error) begin
    $display("FAIL serial framing error");
    bad = bad + 1;
   end
   case (sync_state)
    0: begin
     if (rx_data == 8'hA5) begin sync_state <= 1; crc <= crc_step(16'hFFFF, rx_data); end
    end
    1: begin
     if (rx_data == 8'h5A) begin
      sync_state <= 2; n <= 0; crc <= crc_step(crc, rx_data);
     end else if (rx_data != 8'hA5) begin
      sync_state <= 0;
     end
    end
    default: begin
     frm[n] <= rx_data;
     if (n <= 6 || n <= 6 + len) crc <= crc_step(crc, rx_data);   // header + payload only
     if (n == 6) len = {rx_data, frm[5]};
     n <= n + 1;
     if (n == 7 + len + 1) begin                 // last byte = CRC high
      /* ---- header ---- */
      if (frm[0] != 8'h01) begin $display("FAIL type %02x", frm[0]); bad = bad + 1; end
      if (frm[2] != OUT_W) begin $display("FAIL width %0d", frm[2]); bad = bad + 1; end
      if (frm[3] != OUT_H) begin $display("FAIL height %0d", frm[3]); bad = bad + 1; end
      if (frm[4] != FMT) begin $display("FAIL format %02x", frm[4]); bad = bad + 1; end
      if (len != LEN) begin $display("FAIL length %0d", len); bad = bad + 1; end
      /* ---- CRC ---- */
      crc_lo_hi = {rx_data, frm[7 + len]};
      if (crc_lo_hi !== crc) begin
       if (!RECOVERY) begin
        $display("FAIL crc got %04x want %04x", crc_lo_hi, crc);
        bad = bad + 1;
       end
      end else begin
      /* ---- every pixel ---- */
      pix_bad = 0;
      for (i = 0; i < NPIX; i = i + 1) begin
       got = FMT == 0 ? {frm[7 + 2 * i + 1], frm[7 + 2 * i]} : {8'd0,frm[7+i]};
       j = i / OUT_W;                          // row
       k = i % OUT_W;                          // column
       r8 = (SX * k) & 8'hFF;
       g8 = (SY * j) & 8'hFF;
       b8 = ((SX * k) + (SY * j)) & 8'hFF;
       exp = FMT == 0 ? {r8[7:3],g8[7:2],b8[7:3]} : {8'd0,r8[7:5],g8[7:5],b8[7:6]};
       if (got !== exp) begin
        if (pix_bad < 4)
         $display("FAIL pixel %0d (%0d,%0d) got %04x want %04x", i, k, j, got, exp);
        pix_bad = pix_bad + 1;
       end
      end
      if (pix_bad != 0) begin
       $display("FAIL %0d of %0d pixels wrong", pix_bad, NPIX);
       bad = bad + 1;
      end else begin
       good = good + 1;
       $display("OK frame %0d seq=%02x %0dx%0d len=%0d crc=%04x", good, frm[1], frm[2], frm[3], len, crc);
      end
      end
      sync_state <= 0;
     end
    end
   endcase
  end
 end

 /* ---------------- run ---------------- */
 integer peak_level=0;
 always @(posedge pc) if(!prst && fifo_level>peak_level) peak_level=fifo_level;
 initial begin
  // Waveforms are only useful when debugging; enable with +define+DUMP or
  //   iverilog -DDUMP ...  (a full run would otherwise write a ~75 MB VCD)
`ifdef DUMP
  $dumpfile("stream_link_tb.vcd");
  $dumpvars(0, stream_link_tb);
`endif
  repeat (20) @(posedge pc);
  repeat (20) @(posedge clk);
  prst = 1'b0; rst = 1'b0;
  // 12 display frames of simulated time is enough for the pacing to release three transmissions
  #( (FULL_SIZE ? 8 : 12) * LINE * FRAME_LINES * 2 * PIX_HALF);
  $display("tap captured=%0d dropped=%0d | link frames=%0d bytes=%0d aborts=%0d",
           tap_frames, tap_drops, link_frames, link_bytes, link_aborts);
  $display("FIFO peak=%0d capacity=%0d format=%0d",peak_level,1<<AW,FMT);
  if (tap_drops !== (RECOVERY ? 1 : 0)) begin $display("FAIL tap dropped %0d frames", tap_drops); bad = bad + 1; end
  if (link_aborts !== (RECOVERY ? 1 : 0)) begin $display("FAIL link aborted %0d frames", link_aborts); bad = bad + 1; end
  if (good < 3) begin $display("FAIL only %0d good frames", good); bad = bad + 1; end
  if (bad == 0) $display("PASS tap decimation, framing, CRC and pixel values");
  else          $fatal(1, "FAIL %0d checks", bad);
  $finish;
 end

 initial begin
  #(60 * LINE * FRAME_LINES * 2 * PIX_HALF);
  $fatal(1, "FAIL timeout");
 end
 initial if (RECOVERY) begin
  force link.rready = 1'b0;
  wait(tap_drops != 0);
  release link.rready;
 end
endmodule
