// Per-frame hand statistics over the 640x480 camera RGB stream (camera clock domain).
//
// NOTE: this module is NOT wired into ti60f225_oob_top.v and NOT in ti60f225_oob.xml.
// The Ti60F225 is already at 100% logic utilisation (60800 XLRs; this module alone
// adds ~1700 primitives and pushes place-and-route over capacity), so the gesture
// feature ships on the ESP32 instead (motion centroid over the 96x54 preview stream).
// See wifi_stream/README.md section 6.  This file + sim/gesture_tb.v are kept as the
// FPGA-side design, unit-tested, ready to enable if the team ever frees logic cells.
//
// Gesture recognition needs no frame buffer: a wave is "the centroid of hand pixels
// moved steadily in one direction".  This module reduces each frame to counters -
// a hand pixel is skin-coloured AND sits on an intensity edge - differing from the
// line above (a one-row luma buffer, one RAM10 via simple_dual_port_ram) or from its
// left neighbour.  That reduces a waving hand to its outline; the outline centroid
// tracks the hand's centroid, which is all the firmware gesture machine needs.  The
// RISC-V reads the
// counters over APB and runs the gesture state machine in firmware, where booth-time
// tuning is a recompile instead of a resynthesis.
//
// Skin and motion thresholds come in on cfg (written from firmware via sc_apb_regs,
// quasi-static - written once at boot, stable thereafter):
//   cfg[7:0]   skin_r_min   red floor               (default 95)
//   cfg[15:8]  skin_rg      R must exceed G by this (default 15)
//   cfg[23:16] skin_rb      R must exceed B by this (default 20)
//   cfg[31:24] motion       |G - line above| or |G - left neighbour| threshold (24)
//
// Input stream is the sc_camera_rgb pixel-pair format: rgb_valid carries two
// horizontally adjacent pixels, sof/eof mark the first/last beat of a frame.
// Results latch on eof and hold until the next eof, so the APB side sees values
// that are stable for a whole frame period.
//
// Pipeline: stage 0 captures the beat and reads the row buffer, stage 1 (data back
// from the sync-read RAM) classifies the two pixels and accumulates.  The row buffer
// write happens in stage 1, so a column is always compared against the line above it.
module sc_gesture #(parameter WIDTH=640,HEIGHT=480)(
 input cc,crst,
 input [47:0] rgb,input cv,sof,eof,
 input [31:0] cfg,
 output reg [31:0] o_frames,o_count,o_sx,o_sy,
 output reg [191:0] o_grid);

 // ------------------------------------------------ stage 0: position + RAM read
 reg [9:0] bx;               // pixel-pair column 0..319
 reg [9:0] y;                // line 0..479
 reg p1;reg [47:0] rgb1;reg [9:0] bx1,y1;reg sof1,eof1;   // stage-1 pipeline regs

 // Row buffer: read at stage 0 (raddr = bx), write at stage 1 with the DELAYED
 // address/data (bx1 / rgb1) - at stage 1 bx has already advanced to the next
 // column, so using it here would overwrite the next column before it is read.
 wire [15:0] prev;
 simple_dual_port_ram #(.DATA_WIDTH(16),.ADDR_WIDTH(9),.OUTPUT_REG("FALSE")) row_buf(
  .wdata({rgb1[39:32],rgb1[15:8]}),.waddr(bx1[8:0]),.we(p1),.wclk(cc),
  .re(cv),.raddr(bx[8:0]),.rclk(cc),.rdata(prev));

 always @(posedge cc)begin
  p1<=cv;rgb1<=rgb;bx1<=bx;y1<=y;sof1<=sof;eof1<=eof;
  if(crst)begin bx<=0;y<=0;p1<=0;end
  else if(cv)begin
   if(sof)begin bx<=1;y<=0;end
   else if(bx==10'd319)begin bx<=0;y<=y+1'b1;end
   else bx<=bx+1'b1;
  end
 end

 // -------------------------------------------- stage 1: classify + accumulate
 wire [7:0] r0=rgb1[7:0],g0=rgb1[15:8],b0=rgb1[23:16];
 wire [7:0] r1=rgb1[31:24],g1=rgb1[39:32],b1=rgb1[47:40];
 wire [7:0] t_rmin=cfg[7:0],t_rg=cfg[15:8],t_rb=cfg[23:16],t_mot=cfg[31:24];

 function skin(input [7:0] r,g,b);
  skin=(r>=t_rmin)&&({1'b0,r}>={1'b0,g}+t_rg)&&({1'b0,r}>={1'b0,b}+t_rb)&&(g>8'd40)&&(b>8'd20);
 endfunction

 // vertical edge: this line vs the line above (row buffer); horizontal edge: vs the
 // pixel to the left (g_left = previous beat's g1, 0 at line start).  Either edge
 // marks an outline pixel.
 reg [7:0] g_left;
 wire vedg0=(g0>prev[7:0])?(g0-prev[7:0]>t_mot):(prev[7:0]-g0>t_mot);
 wire vedg1=(g1>prev[15:8])?(g1-prev[15:8]>t_mot):(prev[15:8]-g1>t_mot);
 wire hedg0=(g0>g_left)?(g0-g_left>t_mot):(g_left-g0>t_mot);
 wire hedg1=(g1>g0)?(g1-g0>t_mot):(g0-g1>t_mot);
 wire hand0=skin(r0,g0,b0)&&(vedg0||hedg0);
 wire hand1=skin(r1,g1,b1)&&(vedg1||hedg1);

 wire [9:0] px0={bx1,1'b0},px1={bx1,1'b0}+10'd1;
 wire [1:0] col0=(px0<10'd160)?0:(px0<10'd320)?1:(px0<10'd480)?2:3;
 wire [1:0] col1=(px1<10'd160)?0:(px1<10'd320)?1:(px1<10'd480)?2:3;
 wire [1:0] row1=(y1<10'd160)?0:(y1<10'd320)?1:2;
 wire [3:0] cell0={row1,col0},cell1={row1,col1};

 wire [31:0] add_c={31'd0,hand0}+{31'd0,hand1};
 wire [31:0] add_x=(hand0?{22'd0,px0}:32'd0)+(hand1?{22'd0,px1}:32'd0);
 wire [31:0] add_y=(hand0?{22'd0,y1}:32'd0)+(hand1?{22'd0,y1}:32'd0);

 reg [15:0] grid[0:11];
 reg [31:0] count,sx,sy;
 integer i;

 always @(posedge cc)begin
  if(crst)begin
   count<=0;sx<=0;sy<=0;o_frames<=0;o_count<=0;o_sx<=0;o_sy<=0;o_grid<=0;g_left<=0;
   for(i=0;i<12;i=i+1)grid[i]<=0;
  end else if(p1)begin
   g_left<=(bx1==10'd319)?8'd0:g1;   // beat 0 of the next line compares against 0
   if(sof1)begin
    count<=add_c;sx<=add_x;sy<=add_y;
    for(i=0;i<12;i=i+1)
     grid[i]<={15'd0,(i==cell0&&hand0)}+{15'd0,(i==cell1&&hand1)};
   end else begin
    count<=count+add_c;sx<=sx+add_x;sy<=sy+add_y;
    for(i=0;i<12;i=i+1)
     grid[i]<=grid[i]+{15'd0,(i==cell0&&hand0)}+{15'd0,(i==cell1&&hand1)};
   end
   if(eof1)begin                 // eof1 marks the last beat; the adds above are in
    o_count<=count+add_c;        // flight this cycle, so fold them into the latch
    o_sx<=sx+add_x;o_sy<=sy+add_y;
    o_frames<=o_frames+1'b1;
    for(i=0;i<12;i=i+1)
     o_grid[i*16+:16]<=grid[i]+{15'd0,(i==cell0&&hand0)}+{15'd0,(i==cell1&&hand1)};
   end
  end
 end
endmodule
