// Lock one input through all IN passes. Commit only the final completed output.
// Wait for HDMI to retire its previous bank before starting another output.
module sc_video_schedule #(parameter KEY_CYCLES=1000000)(
 input clk,rst,key_n,input frame_ready,ready_bank,
 output take_frame,output reg release_frame,output reg input_bank,
 input engine_idle,engine_done,engine_ok,input [2:0] styles_ready,
 output reg engine_start,output reg [1:0] engine_style,output reg engine_mode,
 input output_complete,input shown_valid,shown_bank,
 output reg output_bank,publish,publish_bank,
 output reg [1:0] requested_style,output reg [31:0] processed,errors,output [31:0] state_status);
 localparam WAIT=0,START=1,RUN=2,DRAIN=3,SWAP=4;
 reg [2:0] state;wire press,released;
 sc_button #(.CYCLES(KEY_CYCLES)) key(clk,rst,key_n,press,released);
 assign take_frame=state==WAIT&&frame_ready&&engine_idle;
 assign state_status={24'd0,engine_mode,output_bank,input_bank,requested_style,state};
 always @(posedge clk)begin
  engine_start<=0;release_frame<=0;publish<=0;
  if(rst)begin state<=WAIT;input_bank<=0;output_bank<=0;publish_bank<=0;requested_style<=0;engine_style<=0;engine_mode<=0;processed<=0;errors<=0;end
  else begin
   if(press)requested_style<=requested_style==2?0:requested_style+1'b1;
   case(state)
    WAIT:if(take_frame)begin
     input_bank<=ready_bank;output_bank<=shown_valid?!shown_bank:0;
     engine_style<=requested_style;engine_mode<=styles_ready[requested_style];state<=START;
    end
    START:if(engine_idle)begin engine_start<=1;state<=RUN;end
    RUN:if(engine_done)begin
     if(engine_ok)state<=DRAIN;
     else begin errors<=errors+1'b1;release_frame<=1;state<=WAIT;end
    end
    DRAIN:if(output_complete)begin
     publish_bank<=output_bank;publish<=1;release_frame<=1;processed<=processed+1'b1;state<=SWAP;
    end
    SWAP:if(shown_valid&&shown_bank==publish_bank)state<=WAIT;
    default:begin errors<=errors+1'b1;release_frame<=1;state<=WAIT;end
   endcase
  end
 end
endmodule
