// Preview tap for the phone stream, styled-region variant: crop the 640x480 picture out of the
// 1080p display raster, average every 4x4 source pixels into one preview pixel (160x120),
// dither to RGB332 and push one byte per pixel into the asynchronous FIFO that sc_stream_link
// drains.
//
// sc_display drives de / vs / red / green / blue from the 148.5 MHz HDMI pixel clock, so the
// counters here free-run on that clock and never stall the display path.  Capture is only
// enabled or skipped, which keeps this module additive: nothing in the verified display chain
// changes behaviour.
//
// Window: sc_display places the 640x480 picture at
//   mode 0  side by side, stylized on the right, 1.5x nearest: x 960..1919, y 180..899;
//           output pixels repeat source pixels 0,0,1,2,2,3, so phases {0,2,3,5} of every 6
//           are exactly source pixels 0..3 (same pattern for lines);
//   mode 1  stylized 2x, x 320..1599, y 60..1019; phases {0,2,4,6} of every 8;
//   mode 2  original 2x in the same window as mode 1 (there is no stylized picture to show).
// So in every layout a preview pixel is the exact mean of a 4x4 block of the 640x480 picture.
// The layout is sampled once per field from the CPU view register.
//
// Dithering: a 4x4 Bayer threshold is added before truncating to RGB332.
//
// Bands: a full frame does not fit the serial link within one display field, so it is captured
// over BANDS fields.  Band b holds the output rows y with y % BANDS == b; every FIFO word carries
// its band in wd[9:8] and the link copies it into the packet header.  A band that is skipped or
// abandoned is retried on a later field, so bands arrive in order.
module sc_stream_tap #(
 parameter OUT_W      = 160,
 parameter OUT_H      = 120,
 parameter BANDS      = 2,      // fields per full frame, power of two
 parameter PACE_WORDS = 1024    // maximum FIFO occupancy when a band may start
)(
 input             pc,
 input             prst,
 input             de,
 input             vs,
 input      [7:0]  red,
 input      [7:0]  green,
 input      [7:0]  blue,
 input      [1:0]  mode,           // sc_display layout, CPU clock domain
 input             wready,
 input             flush_capture, // asynchronous link-domain recovery request
 input      [13:0] wlevel,
 output reg [15:0] wd,
 output reg        wv,
 output reg        abort_toggle,
 output reg [31:0] tap_frames,     // completed bands
 output reg [31:0] tap_drops
);
 localparam CW = $clog2(OUT_W);
 localparam RW = $clog2(OUT_H);
 localparam BW = (BANDS > 1) ? $clog2(BANDS) : 1;
 localparam HS = 8 + 2;                 // sum of 4 samples
 localparam VS = 8 + 4;                 // sum of 16 samples
 localparam LAST_ROW = OUT_H - BANDS;   // first row of the last row group

 (* async_reg="true" *) reg [1:0] mode1, mode2;
 (* async_reg="true" *) reg flush_meta, flush_sync;
 always @(posedge pc) begin
  mode1 <= mode; mode2 <= mode1;
  if (prst) begin flush_meta <= 0; flush_sync <= 0; end
  else begin flush_meta <= flush_capture; flush_sync <= flush_meta; end
 end

 reg          sbs;       // layout of the current field: 1 = side by side (1.5x), 0 = 2x
 reg [10:0]   xp, yp;    // pixel inside the active line, line inside the field
 reg [2:0]    xs, ys;    // phase inside the block
 reg [CW:0]   xg;        // output column (one extra bit: past the window)
 reg [RW:0]   yg;        // output row
 reg [BW-1:0] band;
 reg          de_d, vs_d, cap;
 reg [HS-1:0] hr, hg, hb;

 wire [10:0] X0   = sbs ? 11'd960 : 11'd320;
 wire [10:0] Y0   = sbs ? 11'd180 : 11'd60;
 wire [2:0]  BL   = sbs ? 3'd5 : 3'd7;      // last phase of a block
 function take(input s, input [2:0] p);    // phase holds a distinct source pixel
  take = s ? (p == 0 || p == 2 || p == 3 || p == 5) : !p[0];
 endfunction

 // Column line buffer: running vertical sums of the three channels.  Read during a block,
 // written back after its last pixel, so read and write never touch the same column at once.
 reg [3*VS-1:0] lb [0:(1<<CW)-1];
 reg [3*VS-1:0] lb_q, lb_wd;
 reg            lb_we;
 reg [CW-1:0]   lb_wa;
 always @(posedge pc) begin
  lb_q <= lb[xg[CW-1:0]];
  if (lb_we) lb[lb_wa] <= lb_wd;
 end

 wire line_end    = de_d & ~de;
 wire frame_start = vs & ~vs_d;
 wire in_x        = de && (xp >= X0) && (xg < OUT_W);
 wire in_y        = (yp >= Y0) && (yg < OUT_H);
 wire row_on      = cap && in_y && ((yg & (BANDS - 1)) == band);
 wire x_take      = take(sbs, xs);
 wire y_take      = take(sbs, ys);
 wire y_first     = (ys == 0);
 wire y_last      = sbs ? (ys == 5) : (ys == 6);
 wire blk_end     = in_x && (xs == BL);

 // Horizontal sum of this block including the current pixel, then the block sum.
 wire [HS-1:0] nr = hr + (x_take ? red   : 8'd0);
 wire [HS-1:0] ng = hg + (x_take ? green : 8'd0);
 wire [HS-1:0] nb = hb + (x_take ? blue  : 8'd0);
 wire [VS-1:0] sr = (y_first ? {VS{1'b0}} : lb_q[3*VS-1:2*VS]) + nr;
 wire [VS-1:0] sg = (y_first ? {VS{1'b0}} : lb_q[2*VS-1:VS])   + ng;
 wire [VS-1:0] sb = (y_first ? {VS{1'b0}} : lb_q[VS-1:0])      + nb;

 // 4x4 Bayer matrix, indexed by the output pixel position.
 reg [3:0] bayer;
 always @* begin
  case ({yg[1:0], xg[1:0]})
   4'h0: bayer = 4'd0;  4'h1: bayer = 4'd8;  4'h2: bayer = 4'd2;  4'h3: bayer = 4'd10;
   4'h4: bayer = 4'd12; 4'h5: bayer = 4'd4;  4'h6: bayer = 4'd14; 4'h7: bayer = 4'd6;
   4'h8: bayer = 4'd3;  4'h9: bayer = 4'd11; 4'hA: bayer = 4'd1;  4'hB: bayer = 4'd9;
   4'hC: bayer = 4'd15; 4'hD: bayer = 4'd7;  4'hE: bayer = 4'd13; default: bayer = 4'd5;
  endcase
 end
 wire [7:0] ar = sr[VS-1:4], ag = sg[VS-1:4], ab = sb[VS-1:4];
 wire [8:0] dr = ar + {bayer, 1'b0};          // 3-bit channel: step 32, threshold 0..30
 wire [8:0] dg = ag + {bayer, 1'b0};
 wire [8:0] db = ab + {bayer, 2'b0};          // 2-bit channel: step 64, threshold 0..60
 wire [2:0] qr = dr[8] ? 3'd7 : dr[7:5];
 wire [2:0] qg = dg[8] ? 3'd7 : dg[7:5];
 wire [1:0] qb = db[8] ? 2'd3 : db[7:6];

 wire band_done = (yg == LAST_ROW + band) && (xg == OUT_W - 1);
 wire [1:0] band2 = band;

 always @(posedge pc) begin
  if (prst) begin
   sbs <= 1'b1; xp <= 0; yp <= 0; xs <= 0; ys <= 0; xg <= 0; yg <= 0; band <= 0;
   de_d <= 1'b0; vs_d <= 1'b0; cap <= 1'b0; lb_we <= 1'b0;
   hr <= 0; hg <= 0; hb <= 0;
   wd <= 16'd0; wv <= 1'b0; abort_toggle <= 1'b0;
   tap_frames <= 32'd0; tap_drops <= 32'd0;
  end else begin
   de_d  <= de;
   vs_d  <= vs;
   wv    <= 1'b0;
   lb_we <= 1'b0;

   if (frame_start) begin
    xp <= 0; yp <= 0; xs <= 0; ys <= 0; xg <= 0; yg <= 0;
    sbs <= (mode2 == 2'd0);
    cap <= (wlevel <= PACE_WORDS[13:0]);      // decide once per field, before the first row
   end else begin
    if (de) begin
     xp <= xp + 1'b1;
     if (xp >= X0) begin
      if (xs == BL) begin xs <= 0; xg <= xg + 1'b1; end
      else xs <= xs + 1'b1;
     end
     hr <= (xs == 0) ? red   : nr;               // phase 0 always takes its pixel
     hg <= (xs == 0) ? green : ng;
     hb <= (xs == 0) ? blue  : nb;
    end else begin
     xp <= 0; xs <= 0; xg <= 0;
    end

    if (blk_end && row_on && y_take) begin
     if (y_last) begin
      if (wready) begin
       wd <= {6'd0, band2, qr, qg, qb};
       wv <= 1'b1;
       if (band_done) begin
        cap  <= 1'b0;                          // one band per field
        band <= band + 1'b1;
        tap_frames <= tap_frames + 1'b1;
       end
      end else begin
       // The FIFO is full: the display cannot be stalled, so the band is abandoned.  The link
       // sees abort_toggle and flushes; the same band is retried on a later field.
       cap <= 1'b0;
       abort_toggle <= ~abort_toggle;
       tap_drops <= tap_drops + 1'b1;
      end
     end else begin
      lb_wd <= {sr, sg, sb};
      lb_wa <= xg[CW-1:0];
      lb_we <= 1'b1;
     end
    end

    if (line_end) begin
     yp <= yp + 1'b1;
     if (yp >= Y0) begin
      if (ys == BL) begin ys <= 0; yg <= yg + 1'b1; end
      else ys <= ys + 1'b1;
     end
    end
   end
   // Hold capture off during recovery. On release, only a later field boundary can rearm it.
   if (flush_sync) begin cap <= 1'b0; wv <= 1'b0; end
  end
 end
endmodule
