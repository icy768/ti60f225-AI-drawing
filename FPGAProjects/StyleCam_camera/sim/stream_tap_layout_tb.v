// Phone preview tap, every display layout: a 1080p60 raster draws a 640x480 test picture where
// sc_display would place it for MODE (nearest 1.5x / 2x / 1x), white elsewhere; every tap word
// of one full frame (both bands) is written to OUT for sim_stream_tap_layouts.py to check.
`timescale 1ns / 1ps
module stream_tap_layout_tb #(parameter MODE=0, parameter OUT="tap_words.txt");
 reg pc = 1'b0, prst = 1'b1;
 always #3.367 pc = ~pc;
 reg [11:0] x = 0, y = 0;
 always @(posedge pc) begin
  if (x == 2199) begin x <= 0; y <= (y == 1124) ? 0 : y + 1; end else x <= x + 1;
 end
 wire de = (x < 1920) && (y < 1080);
 wire vs = (y >= 1084) && (y < 1089);
 integer X0, Y0, sx, sy, inwin;
 always @* begin
  case (MODE)
   0: begin X0 = 960; Y0 = 180; end
   3: begin X0 = 640; Y0 = 300; end
   4: begin X0 = 480; Y0 = 180; end
   default: begin X0 = 320; Y0 = 60; end
  endcase
  if (MODE == 0 || MODE == 4) begin
   sx = ((x - X0) * 2) / 3; sy = ((y - Y0) * 2) / 3; inwin = x >= X0 && x < X0 + 960 && y >= Y0 && y < Y0 + 720;
  end else if (MODE == 3) begin
   sx = x - X0; sy = y - Y0; inwin = x >= X0 && x < X0 + 640 && y >= Y0 && y < Y0 + 480;
  end else begin
   sx = (x - X0) / 2; sy = (y - Y0) / 2; inwin = x >= X0 && x < X0 + 1280 && y >= Y0 && y < Y0 + 960;
  end
 end
 wire [7:0] red   = inwin ? 8'(sx * 7 + sy * 3) : 8'hff;
 wire [7:0] green = inwin ? 8'(sx * 2 + sy * 9 + 17) : 8'hff;
 wire [7:0] blue  = inwin ? 8'((sx >> 1) ^ sy) : 8'hff;
 wire [15:0] wd; wire wv, abort_toggle; wire [31:0] tap_frames, tap_drops;
 sc_stream_tap #(.OUT_W(160), .OUT_H(120), .BANDS(2), .PACE_WORDS(1024)) tap(
  .pc(pc), .prst(prst), .de(de), .vs(vs), .red(red), .green(green), .blue(blue), .mode(3'(MODE)),
  .wready(1'b1), .flush_capture(1'b0), .wlevel(14'd0), .wd(wd), .wv(wv),
  .abort_toggle(abort_toggle), .tap_frames(tap_frames), .tap_drops(tap_drops));
 integer f, words = 0;
 always @(posedge pc) if (!prst && wv) begin $fdisplay(f, "%h", wd[9:0]); words = words + 1; end
 initial begin
  f = $fopen(OUT, "w");
  repeat (10) @(posedge pc); prst = 1'b0;
  wait (tap_frames == 2); repeat (10) @(posedge pc);
  $fclose(f);
  $display("DONE mode=%0d words=%0d drops=%0d", MODE, words, tap_drops);
  $finish;
 end
 initial begin #100000000; $fatal(1, "timeout"); end
endmodule
