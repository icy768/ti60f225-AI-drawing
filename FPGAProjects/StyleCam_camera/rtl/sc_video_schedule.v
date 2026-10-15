// Three output banks decouple compute from vertical-blank retirement.
// One published descriptor may wait for HDMI while another bank is written.
module sc_video_schedule(
 input clk,rst,input run,step,input [1:0] style_req,input frame_ready,input [1:0] ready_bank,
 output take_frame,output reg release_frame,output reg [1:0] input_bank,output hold_swap,
 input engine_idle,engine_done,engine_ok,input [2:0] styles_ready,
 output reg engine_start,output reg [1:0] engine_style,output reg engine_mode,
 input output_complete,input shown_valid,input [1:0] shown_bank,
 output reg [1:0] output_bank,output reg publish,output reg [1:0] publish_bank,
 output reg [1:0] requested_style,output reg [31:0] processed,errors,output [31:0] state_status,
 output reg [31:0] clock_cycles,scan_sequence,scan_timestamp,publish_wait_cycles,
 output reg [1:0] scan_style);
 localparam WAIT=0,START=1,RUN=2,DRAIN=3;
 reg [2:0] state;reg armed,pending;
 reg [31:0] pending_timestamp,pending_sequence;reg [1:0] pending_style;
 wire [2:0] unavailable=({3{shown_valid}}&(3'b001<<shown_bank))|
                        ({3{pending}}&(3'b001<<publish_bank));
 wire [1:0] free_bank=!unavailable[0]?2'd0:!unavailable[1]?2'd1:2'd2;
 assign take_frame=state==WAIT&&frame_ready&&engine_idle&&(run||armed)&&!(&unavailable);
 // Keep the existing firmware's low-bit layout; full bank ownership is internal.
 assign state_status={21'd0,engine_style,engine_mode,output_bank[0],input_bank,requested_style,state};
 assign hold_swap=pending&&shown_valid&&shown_bank==publish_bank;
 always @(posedge clk)begin
  engine_start<=0;release_frame<=0;publish<=0;
  if(rst)begin
   state<=WAIT;input_bank<=0;output_bank<=0;publish_bank<=0;requested_style<=0;
   engine_style<=0;engine_mode<=0;processed<=0;errors<=0;armed<=0;pending<=0;
   clock_cycles<=0;scan_sequence<=0;scan_timestamp<=0;publish_wait_cycles<=0;scan_style<=0;
   pending_timestamp<=0;pending_sequence<=0;pending_style<=0;
  end else begin
   clock_cycles<=clock_cycles+1'b1;
   requested_style<=style_req>2?2'd0:style_req;
   if(step)armed<=1;else if(take_frame)armed<=0;
   if(hold_swap)begin
    pending<=0;scan_sequence<=pending_sequence;scan_style<=pending_style;
    scan_timestamp<=clock_cycles;publish_wait_cycles<=clock_cycles-pending_timestamp;
   end
   case(state)
    WAIT:if(take_frame)begin
     input_bank<=ready_bank;output_bank<=free_bank;
     engine_style<=requested_style;engine_mode<=styles_ready[requested_style];state<=START;
    end
    START:if(engine_idle)begin engine_start<=1;state<=RUN;end
    RUN:if(engine_done)begin
     if(engine_ok)state<=DRAIN;
     else begin errors<=errors+1'b1;release_frame<=1;state<=WAIT;end
    end
    // Do not publish on the retirement cycle: capture must transfer the old
    // pending original to DISPLAYED before recording the next pending input.
    DRAIN:if(output_complete&&!pending)begin
     publish_bank<=output_bank;publish<=1;release_frame<=1;processed<=processed+1'b1;
     pending<=1;pending_timestamp<=clock_cycles;pending_sequence<=processed+1'b1;
     pending_style<=engine_style;state<=WAIT;
    end
    default:begin errors<=errors+1'b1;release_frame<=1;state<=WAIT;end
   endcase
  end
 end
endmodule
