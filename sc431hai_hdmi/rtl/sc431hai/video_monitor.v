// Diagnostics are passive: never stall CSI, framebuffer or HDMI.
module video_monitor #(
 parameter integer REPORT_CYCLES=25000000, WAIT_CYCLES=250000,
 parameter integer UART_CYCLES=217, THUMB_REQUEST_CYCLES=200000000
)(
 input wire ref_clk,reset,pixel_clk,byte_clk,vs,de,irq,ddr_ready,
 input wire [1:0] vc,
 input wire [5:0] dt,
 input wire [15:0] wc,setup_status,
 input wire [3:0] ppc,
 input wire [31:0] raw_pixels,
 input wire [287:0] diagnostic_words,
 input wire diagnostic_valid,
 output wire uart_tx
);
 wire [223:0] pixel_values;
 sc_frame_stats stats(.clk(pixel_clk),.reset(reset),.vs(vs),.de(de),
   .vc(vc),.dt(dt),.wc(wc),.ppc(ppc),.irq(irq),.raw_pixels(raw_pixels),.values(pixel_values));
 reg [31:0] byte_count;
 always @(posedge byte_clk or posedge reset)
   if(reset) byte_count<=0; else byte_count<=byte_count+1'b1;
 reg [31:0] ref_count,report_count;
 wire request=report_count==0;
 wire [223:0] pixel_snapshot;
 wire [31:0] byte_snapshot;
 wire pixel_done,byte_done;
 snapshot_cdc #(.WIDTH(224)) pixel_bridge(.src_clk(pixel_clk),.dst_clk(ref_clk),.reset(reset),
   .request(request),.src_data(pixel_values),.dst_data(pixel_snapshot),.done(pixel_done));
 snapshot_cdc #(.WIDTH(32)) byte_bridge(.src_clk(byte_clk),.dst_clk(ref_clk),.reset(reset),
   .request(request),.src_data(byte_count),.dst_data(byte_snapshot),.done(byte_done));
 (* async_reg="true" *) reg [1:0] ddr_sync;
 reg pixel_fresh,byte_fresh;
 reg [319:0] report;
 reg send;
 wire busy,status_tx,thumb_tx,thumb_active,thumb_want;
 wire overview_tx,overview_active,overview_want;
 reg diag_active,diag_sent,diag_start;
 reg [1:0] diag_state;
 wire diag_busy,diag_tx;
 wire diag_want=diagnostic_valid && !diag_sent;
 // Paper's left edge located from the 2026-10-03 overview; origin stays Bayer-aligned.
 raw_thumbnail #(.UART_CYCLES(UART_CYCLES),.ROI_MODE(1),.X0(512),.Y0(504)) thumbnail(.pixel_clk(pixel_clk),.ref_clk(ref_clk),.reset(reset),
   .request(ref_count>=THUMB_REQUEST_CYCLES),.vs(vs),.valid(de && vc==0 && dt==6'h2b && ppc==4),
   .raw_pixels(raw_pixels),.permit(!busy && !send && !diag_active && !diag_want && !overview_active),
   .want(thumb_want),.active(thumb_active),.tx(thumb_tx));
 // Capture the same frame's overview to locate the contiguous ROI.
 // ROI transfer has priority; frozen overview RAM waits without stalling video.
 raw_thumbnail #(.UART_CYCLES(UART_CYCLES),.ROI_MODE(0)) overview(.pixel_clk(pixel_clk),.ref_clk(ref_clk),.reset(reset),
   .request(ref_count>=THUMB_REQUEST_CYCLES),.vs(vs),.valid(de && vc==0 && dt==6'h2b && ppc==4),
   .raw_pixels(raw_pixels),.permit(!busy && !send && !diag_active && !diag_want && !thumb_active && !thumb_want),
   .want(overview_want),.active(overview_active),.tx(overview_tx));
 assign uart_tx=diag_active?diag_tx:(thumb_active?thumb_tx:(overview_active?overview_tx:status_tx));
 video_uart #(.CYCLES(UART_CYCLES),.MAGIC("SCE1")) exposure_uart(
   .clk(ref_clk),.reset(reset),.start(diag_start),
   .words({ref_count,diagnostic_words}),.tx(diag_tx),.busy(diag_busy));
 // One register record, after configuration. Never interrupt another UART line.
 always @(posedge ref_clk) begin
   if(reset) begin diag_active<=0;diag_sent<=0;diag_start<=0;diag_state<=0;end
   else begin
     diag_start<=0;
     if(!diag_active) begin
       if(diag_want && !busy && !send && !thumb_active && !overview_active) begin
         diag_active<=1;diag_start<=1;diag_state<=0;
       end
     end else if(diag_state==0) begin
       if(diag_busy) diag_state<=1;
     end else if(!diag_busy) begin diag_active<=0;diag_sent<=1;end
   end
 end
 video_uart #(.CYCLES(UART_CYCLES)) uart(.clk(ref_clk),.reset(reset),.start(send),
   .words(report),.tx(status_tx),.busy(busy));
 always @(posedge ref_clk) begin
   if(reset) begin
     ref_count<=0;report_count<=0;pixel_fresh<=0;byte_fresh<=0;
     ddr_sync<=0;report<=0;send<=0;
   end else begin
     ref_count<=ref_count+1'b1;
     report_count<=(report_count==REPORT_CYCLES-1)?0:report_count+1'b1;
     ddr_sync<={ddr_sync[0],ddr_ready};send<=0;
     if(request) begin pixel_fresh<=0;byte_fresh<=0;end
     else begin
       if(pixel_done) pixel_fresh<=1;
       if(byte_done) byte_fresh<=1;
     end
     // Bound the wait even when the camera provides no recovered byte clock.
     if(report_count==WAIT_CYCLES && !busy && !thumb_active && !thumb_want && !overview_active && !overview_want && !diag_active && !diag_want) begin
       report<={ref_count,13'd0,byte_fresh,pixel_fresh,ddr_sync[1],setup_status,
         pixel_snapshot,byte_snapshot};
       send<=1;
     end
   end
 end
endmodule

// Source data is captured before ACK; it stays stable until the next request.
// A stopped source clock leaves pending asserted, so requests never alias.
module snapshot_cdc #(parameter WIDTH=32)(
 input wire src_clk,dst_clk,reset,request,
 input wire [WIDTH-1:0] src_data,
 output reg [WIDTH-1:0] dst_data,
 output reg done
);
 reg req,ack,pending;
 reg [WIDTH-1:0] held;
 (* async_reg="true" *) reg [1:0] req_sync;
 (* async_reg="true" *) reg [2:0] ack_sync;
 always @(posedge src_clk or posedge reset) begin
   if(reset) begin req_sync<=0;ack<=0;held<=0;end
   else begin
     req_sync<={req_sync[0],req};
     if(req_sync[1]!=ack) begin held<=src_data;ack<=req_sync[1];end
   end
 end
 always @(posedge dst_clk or posedge reset) begin
   if(reset) begin req<=0;pending<=0;ack_sync<=0;dst_data<=0;done<=0;end
   else begin
     ack_sync<={ack_sync[1:0],ack};done<=0;
     if(request && !pending) begin req<=~req;pending<=1;end
     if(pending && ack_sync[2]==req) begin dst_data<=held;pending<=0;done<=1;end
   end
 end
endmodule

module sc_frame_stats #(
 parameter [31:0] FRAME_PIXELS=2073600,
 parameter [15:0] LINE_BYTES=2400
)(
 input wire clk,reset,vs,de,irq,
 input wire [1:0] vc,
 input wire [5:0] dt,
 input wire [15:0] wc,
 input wire [3:0] ppc,
 input wire [31:0] raw_pixels,
 output wire [223:0] values
);
 reg vs_d,seen_blank,armed,bad;
 reg [31:0] good_count,bad_count,pixels,last_pixels,last_format;
 reg [31:0] ticks,start_tick,period,irq_count,checksum,last_checksum;
 reg started,irq_d;
 (* async_reg="true" *) reg [1:0] irq_sync;
 wire raw_valid=de && vc==0 && dt==6'h2b;
 wire invalid=de && dt!=6'h12 && (!raw_valid || wc!=LINE_BYTES || ppc!=4);
 assign values={good_count,bad_count,last_pixels,last_format,period,irq_count,last_checksum};
 always @(posedge clk or posedge reset) begin
   if(reset) begin
     vs_d<=0;seen_blank<=0;armed<=0;bad<=0;pixels<=0;last_pixels<=0;
     good_count<=0;bad_count<=0;last_format<=0;ticks<=0;start_tick<=0;period<=0;
     started<=0;irq_count<=0;irq_sync<=0;irq_d<=0;checksum<=0;last_checksum<=0;
   end else begin
     ticks<=ticks+1'b1;vs_d<=vs;
     irq_sync<={irq_sync[0],irq};irq_d<=irq_sync[1];
     if(irq_sync[1] && !irq_d) irq_count<=irq_count+1'b1;
     if(!vs) seen_blank<=1;
     if(de) last_format<={4'd0,vc,dt,ppc,wc};
     if(vs && !vs_d && seen_blank) begin
       if(started) period<=ticks-start_tick;
       started<=1;start_tick<=ticks;armed<=1;bad<=invalid;
       pixels<=raw_valid?{28'd0,ppc}:32'd0;
       checksum<=raw_valid?raw_pixels:32'd0;
     end else if(armed && vs) begin
       if(invalid) bad<=1;
       if(raw_valid) begin
         pixels<=pixels+{28'd0,ppc};checksum<=checksum+raw_pixels;
         if(pixels>=FRAME_PIXELS) bad<=1;
       end
     end
     if(armed && vs_d && !vs) begin
       armed<=0;last_pixels<=pixels;last_checksum<=checksum;
       if(pixels==FRAME_PIXELS && !bad && !de) good_count<=good_count+1'b1;
       else bad_count<=bad_count+1'b1;
     end
   end
 end
endmodule
