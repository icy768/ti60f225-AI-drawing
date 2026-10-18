// Preview tap for the phone stream: decimate the 1080p display raster down to OUT_W x OUT_H
// RGB565 words and push them into the asynchronous FIFO that sc_stream_link drains.
//
// sc_display drives de / vs / red / green / blue from the 148.5 MHz HDMI pixel clock, so the
// sample counters here free-run on that clock and never stall the display path.  Capture is
// only enabled or skipped, which keeps this module additive: nothing in the verified display
// chain changes behaviour.
//
// The grid is locked to the display field: vs marks the end of the active area, so the frame
// that follows always starts at the first active line with the horizontal counter at zero.
// Every SX-th active pixel of every SY-th active line is kept, i.e. 1920x1080 with SX=SY=20
// gives exactly 96x54 pixels.
//
// Pacing: 96x54 RGB565 is 10368 B per frame, roughly twice what a 3 Mbaud link can carry in a
// 16.7 ms display frame.  A frame is captured only when the FIFO already holds at most
// PACE_WORDS. Peak occupancy is the starting level plus the captured words minus the words
// drained concurrently. Skipped frames leave the previous image on the phone, so
// the preview stays continuous and the effective rate regulates itself.
module sc_stream_tap #(
 parameter SRC_W      = 1920,   // active pixels per display line (1080p60)
 parameter SRC_H      = 1080,   // active display lines per frame
 parameter SX         = 20,     // horizontal decimation, OUT_W = SRC_W/SX
 parameter SY         = 20,     // vertical   decimation, OUT_H = SRC_H/SY
 parameter PACE_WORDS = 1024,   // maximum FIFO occupancy when a frame may start
 parameter FMT        = 0      // 0: RGB565, 1: RGB332 in wd[7:0]
)(
 input             pc,
 input             prst,
 input             de,
 input             vs,
 input      [7:0]  red,
 input      [7:0]  green,
 input      [7:0]  blue,
 input             wready,
 input             flush_capture, // asynchronous link-domain recovery request
 input      [12:0] wlevel,
 output reg [15:0] wd,
 output reg        wv,
 output reg        abort_toggle,
 output reg [31:0] tap_frames,
 output reg [31:0] tap_drops
);
 localparam OUT_W = SRC_W / SX;
 localparam OUT_H = SRC_H / SY;
 localparam NPIX  = OUT_W * OUT_H;
 localparam XW    = (SX > 1) ? $clog2(SX) : 1;
 localparam YW    = (SY > 1) ? $clog2(SY) : 1;
 localparam PW    = $clog2(NPIX + 1);     // pixels sent inside the frame being captured

 reg [XW-1:0] xs;        // 0 .. SX-1, restarts at every active line
 reg [YW-1:0] ys;        // 0 .. SY-1, advances at every active line
 reg [PW-1:0] spix;      // pixels already written for the frame being captured
 reg          de_d, vs_d, cap;
 (* async_reg="true" *) reg flush_meta, flush_sync;
 always @(posedge pc) begin
  if (prst) begin flush_meta <= 0; flush_sync <= 0; end
  else begin flush_meta <= flush_capture; flush_sync <= flush_meta; end
 end

 wire line_end    = de_d & ~de;                    // first pixel-clock after an active line
 wire frame_start = vs & ~vs_d;                    // field boundary, inside vertical blanking
 wire sample      = de & (xs == 0) & (ys == 0);    // grid position of the preview frame
 wire last_pix    = (spix == NPIX - 1);

 always @(posedge pc) begin
  if (prst) begin
   xs <= 0; ys <= 0; spix <= 0; de_d <= 1'b0; vs_d <= 1'b0; cap <= 1'b0;
   wd <= 16'd0; wv <= 1'b0; abort_toggle <= 1'b0;
   tap_frames <= 32'd0; tap_drops <= 32'd0;
  end else begin
   de_d <= de;
   vs_d <= vs;
   wv   <= 1'b0;

   if (frame_start) begin
    xs   <= {XW{1'b0}};
    ys   <= {YW{1'b0}};
    spix <= 0;
    cap  <= (wlevel <= PACE_WORDS[12:0]);     // decide once per frame, before the first sample
   end else if (cap && wv && !wready) begin
    cap <= 1'b0;
    abort_toggle <= ~abort_toggle;
    tap_drops <= tap_drops + 1'b1;
   end else begin
    if (de) begin
     xs <= (xs == SX - 1) ? {XW{1'b0}} : xs + 1'b1;
     if (sample) begin
      if (cap && wready) begin
       wd <= (FMT == 1) ? {8'd0,red[7:5],green[7:5],blue[7:6]} :
                         {red[7:3],green[7:2],blue[7:3]};
       wv <= 1'b1;
       if (last_pix) begin spix <= 0; tap_frames <= tap_frames + 1'b1; end
       else                spix <= spix + 1'b1;
      end else if (cap) begin
       // The FIFO is full: the display cannot be stalled, so the frame is abandoned.  The link
       // sees abort_toggle and flushes; the phone discards the short frame and resynchronises.
       cap <= 1'b0;
       abort_toggle <= ~abort_toggle;
       tap_drops <= tap_drops + 1'b1;
      end
     end
    end else begin
     xs <= {XW{1'b0}};
    end

    if (line_end) begin
     ys <= (ys == SY - 1) ? {YW{1'b0}} : ys + 1'b1;
    end
   end
   // Hold capture off during recovery. On release, only a later field boundary can rearm it.
   if (flush_sync) begin cap <= 1'b0; wv <= 1'b0; end
  end
 end
endmodule
