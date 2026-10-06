// One passive RAW8 snapshot: decimated overview or a contiguous center ROI.
// No control path back to the receiver or display. RAM freezes until reset.
module raw_thumbnail #(
 parameter integer WIDTH=1920, HEIGHT=1080, STRIDE=15,
 parameter integer OUT_W=128, OUT_H=72, UART_CYCLES=217, ROI_MODE=0,
 parameter integer X0=(WIDTH-OUT_W)/2, Y0=(HEIGHT-OUT_H)/2
)(
 input wire pixel_clk,ref_clk,reset,request,vs,valid,permit,
 input wire [31:0] raw_pixels,
 output wire want,
 output reg active,
 output wire tx
);
 localparam TOTAL=OUT_W*OUT_H, BLOCKS=TOTAL/32;
 (* async_reg="true" *) reg [1:0] req_sync;
 reg vs_d,blank_seen,capturing,captured;
 reg [11:0] x,y,next_x,next_y;
 reg [13:0] wr_addr;
 wire sample=capturing && wr_addr<TOTAL && vs && valid &&
   (ROI_MODE ? (x>=X0 && x<X0+OUT_W && y>=Y0 && y<Y0+OUT_H) :
               (y==next_y && next_x>=x && next_x<x+4));
 always @(posedge pixel_clk or posedge reset) begin
   if(reset) begin
     req_sync<=0;vs_d<=0;blank_seen<=0;capturing<=0;captured<=0;
     x<=0;y<=0;next_x<=0;next_y<=0;wr_addr<=0;
   end else begin
     req_sync<={req_sync[0],request};vs_d<=vs;
     if(!vs) blank_seen<=1;
     if(req_sync[1] && blank_seen && vs && !vs_d && !captured) begin
       capturing<=1;x<=0;y<=0;next_x<=0;next_y<=0;wr_addr<=0;
     end else if(capturing && vs && valid) begin
       if(sample) begin
         wr_addr<=wr_addr+(ROI_MODE?4:1);next_x<=next_x+STRIDE;
       end
       if(x==WIDTH-4) begin
         x<=0;y<=y+1'b1;next_x<=0;
         if(y==next_y) next_y<=next_y+STRIDE;
       end else x<=x+4;
     end
     if(vs_d && !vs) begin
       if(capturing && wr_addr==TOTAL && y==HEIGHT && x==0) captured<=1;
       capturing<=0; // incomplete snapshots retry at the next frame
     end
   end
 end
 (* async_reg="true" *) reg [2:0] ready_sync;
 reg sent;
 assign want=ready_sync[2] && !sent;
 reg [13:0] rd_addr;
 wire [7:0] rd_data;
 generate if(ROI_MODE) begin: roi_storage
   // X0 and OUT_W are multiples of four. Keep all four adjacent input pixels.
   reg [31:0] memory[0:TOTAL/4-1];
   reg [31:0] read_word;
   reg [1:0] read_lane;
   always @(posedge pixel_clk) if(sample) memory[wr_addr[13:2]]<=raw_pixels;
   always @(posedge ref_clk) begin
     read_word<=memory[rd_addr[13:2]];read_lane<=rd_addr[1:0];
   end
   assign rd_data=read_word[read_lane*8 +: 8];
 end else begin: overview_storage
   reg [7:0] memory[0:TOTAL-1];
   reg [7:0] read_byte;
   always @(posedge pixel_clk)
     if(sample) memory[wr_addr]<=raw_pixels[next_x[1:0]*8 +: 8];
   always @(posedge ref_clk) read_byte<=memory[rd_addr];
   assign rd_data=read_byte;
 end endgenerate
 reg [255:0] payload;
 reg [8:0] block_index;
 reg [4:0] byte_index;
 reg [2:0] state;
 reg launch;
 wire busy;
 localparam [15:0] THUMB_WIDTH=OUT_W,THUMB_HEIGHT=OUT_H;
 wire [319:0] words={THUMB_WIDTH,THUMB_HEIGHT,23'd0,block_index,payload};
 video_uart #(.CYCLES(UART_CYCLES),.MAGIC(ROI_MODE?"ROI1":"RAW1")) uart(
   .clk(ref_clk),.reset(reset),.start(launch),.words(words),.tx(tx),.busy(busy));
 always @(posedge ref_clk or posedge reset) begin
   if(reset) begin
     ready_sync<=0;sent<=0;active<=0;rd_addr<=0;payload<=0;
     block_index<=0;byte_index<=0;state<=0;launch<=0;
   end else begin
     ready_sync<={ready_sync[1:0],captured};launch<=0;
     if(!active) begin
       if(want && permit) begin
         active<=1;state<=0;rd_addr<=0;byte_index<=0;block_index<=0;
       end
     end else case(state)
       0:state<=1; // allow synchronous RAM read
       1:begin
         payload<={payload[247:0],rd_data};
         if(byte_index==31) state<=2;
         else begin byte_index<=byte_index+1'b1;rd_addr<=rd_addr+1'b1;state<=0;end
       end
       2:if(!busy) begin launch<=1;state<=3;end
       3:if(busy) state<=4;
       4:if(!busy) begin
         if(block_index==BLOCKS-1) begin active<=0;sent<=1;end
         else begin
           block_index<=block_index+1'b1;byte_index<=0;rd_addr<=rd_addr+1'b1;state<=0;
         end
       end
     endcase
   end
 end
endmodule
