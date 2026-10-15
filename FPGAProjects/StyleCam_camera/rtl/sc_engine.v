// Network execution controller (video path of StyleCam_uart without the host UART protocol).
// One video job: mode 0 = 12 ordered IN calibration passes + final output pass;
// mode 1 = one output pass + one rotating IN layer update (coefficients apply next frame).
// All passes replay the locked input bank from DDR. Internal names follow StyleCam_uart so the
// V21 video-engine bit-exact testbench applies unchanged.
// The RISC-V loads weights (cpu_cfg_sel=1, 32-bit lanes) and IN coefficients (sel=0) through cpu_cfg_*,
// using the records of model/net_blob.bin; writes are accepted only while no job is running.
module sc_engine #(parameter WIDTH=640, HEIGHT=480, N_STYLES=3, IN_TRACE=0, IN_FILE="model/in_constants.mem")(
 input clk,input system_reset,
 input sink_ready,output [23:0] sink_data,output sink_valid,output new_frame,
 input [23:0] replay_data,input replay_valid,output replay_ready,
 output replay_start,input replay_busy,
 input video_start,input [1:0] video_style,input video_mode,
 output video_idle,output reg video_done,video_ok,output [2:0] video_styles_ready,
 input cpu_cfg_we,input cpu_cfg_sel,input [4:0] cpu_cfg_lane,input [4:0] cpu_cfg_layer,input [11:0] cpu_cfg_addr,input [37:0] cpu_cfg_data,output reg cpu_cfg_rejects,
 output reg [31:0] run_cycles,first_output_cycles,input_stalls,output_stalls,
 output reg [31:0] auto_cycles,auto_frames,auto_writes,auto_errors,errors);
 reg [9:0] por=0; always @(posedge clk) if(!(&por)) por<=por+1'b1;
 wire rst=!(&por)||system_reset;
 reg [2:0] state;
 reg [3:0] style; reg active,done;
 reg [31:0] enqueued,consumed,produced;
 reg [4:0] reset_count,tail,st_sel; reg st_arm,st_fs,st_fe;
 wire [39:0] st_s1; wire [59:0] st_s2; wire st_done,st_busy;
 reg cfg_we,cfg_sel; reg [4:0] cfg_lane,cfg_layer; reg [11:0] cfg_addr; reg [37:0] cfg_data;
 reg [2:0] style_ready;
 assign video_styles_ready=style_ready;
 reg video_active;
 reg auto_busy,auto_done,auto_mode;reg [2:0] auto_phase;reg [3:0] auto_layer;
 reg [31:0] auto_math_cycles;
 reg [3:0] rotation[0:2];
 reg in_start;wire in_busy,in_done,in_error,in_cfg_we;wire [7:0] in_idx;
 wire [4:0] in_cfg_layer;wire [11:0] in_cfg_addr;wire [37:0] in_cfg_data,in_trace_data;
 wire [31:0] in_cycles,in_writes;
 assign video_idle=state==0&&!active&&tail==0&&!replay_busy&&!auto_busy&&!in_busy;
 sc_in_refresh #(.WIDTH(WIDTH),.HEIGHT(HEIGHT),.CONSTFILE(IN_FILE),.TRACE(IN_TRACE)) in_update(
 .clk(clk),.rst(rst),.start(in_start),.style(style[1:0]),.layer(auto_layer),
 .busy(in_busy),.done(in_done),.error(in_error),.stats_index(in_idx),.stats_s1(st_s1),.stats_s2(st_s2),
 .cfg_we(in_cfg_we),.cfg_layer(in_cfg_layer),.cfg_addr(in_cfg_addr),.cfg_data(in_cfg_data),
 .trace_index(10'd0),.trace_data(in_trace_data),.cycles(in_cycles),.writes(in_writes));
 wire [23:0] net_data; wire net_valid,net_ready;
 wire nrst=rst||(reset_count!=0);
 wire iv=active&&replay_valid&&!nrst;
 assign replay_ready=active&&net_ready&&!nrst;
 assign replay_start=st_fs;
 assign sink_data=net_data; assign sink_valid=net_valid&&!nrst;
 assign new_frame=st_fs;
 wire take=iv&&net_ready;
 stylenet_top net(.clk(clk),.rst(nrst),.style(style),.cfg_we(cfg_we||in_cfg_we),.cfg_sel(!in_cfg_we&&cfg_sel),
 .cfg_layer(in_cfg_we?in_cfg_layer:cfg_layer),.cfg_lane(in_cfg_we?5'd0:cfg_lane),.cfg_addr(in_cfg_we?in_cfg_addr:cfg_addr),.cfg_data(in_cfg_we?in_cfg_data:cfg_data),
 .i_data(replay_data),.i_valid(iv),.i_ready(net_ready),.o_data(net_data),.o_valid(net_valid),.o_ready(sink_ready),
 .st_sel(st_sel),.st_arm(st_arm),.st_fs(st_fs),.st_fe(st_fe),.st_idx(in_idx),
 .st_s1(st_s1),.st_s2(st_s2),.st_done(st_done),.st_busy(st_busy));
 integer j;
 // state 0 idle, 7 network reset wait
 always @(posedge clk) begin
  video_done<=0; cfg_we<=0; st_arm<=0; st_fs<=0; st_fe<=0;in_start<=0;
  if(rst) begin
   state<=0; reset_count<=0; tail<=0; active<=0; done<=0; style<=0;
   enqueued<=0; consumed<=0; produced<=0; errors<=0; st_sel<=31;
   cfg_sel<=0; cfg_lane<=0; cfg_layer<=0; cfg_addr<=0; cfg_data<=0; cpu_cfg_rejects<=0;
   run_cycles<=0;first_output_cycles<=0;input_stalls<=0;output_stalls<=0;
   style_ready<=0;
   video_active<=0;video_ok<=0;video_done<=0;auto_busy<=0;auto_done<=0;auto_mode<=0;auto_phase<=0;auto_layer<=0;
   auto_cycles<=0;auto_frames<=0;auto_writes<=0;auto_math_cycles<=0;auto_errors<=0;
   for(j=0;j<3;j=j+1)rotation[j]<=0;
  end else begin
   if(reset_count!=0) reset_count<=reset_count-1'b1;
   if(active&&!nrst)begin
    run_cycles<=run_cycles+1'b1;
    if(iv&&!net_ready)input_stalls<=input_stalls+1'b1;
    if(net_valid&&!sink_ready)output_stalls<=output_stalls+1'b1;
   end
   if(take) consumed<=consumed+1'b1;
   if(net_valid&&sink_ready&&!nrst) begin
    if(produced==0)first_output_cycles<=run_cycles+1'b1;
    produced<=produced+1'b1;
    if(produced==WIDTH*HEIGHT-1) begin tail<=16; active<=0; end
   end
   if(tail!=0) begin tail<=tail-1'b1; if(tail==1) begin st_fe<=1;done<=1; end end
   // RISC-V coefficient write: only between jobs (same rule as the host write it replaces)
   if(cpu_cfg_we)begin
    if(state==0&&!active&&tail==0&&!auto_busy&&!in_busy&&cpu_cfg_layer<13)begin
     cfg_sel<=cpu_cfg_sel;cfg_lane<=cpu_cfg_lane;cfg_layer<=cpu_cfg_layer;cfg_addr<=cpu_cfg_addr;cfg_data<=cpu_cfg_data;cfg_we<=1;
    end else cpu_cfg_rejects<=1;
   end
   if(state==7&&reset_count==0)begin active<=1; st_arm<=1; st_fs<=1; state<=0; end
   if(auto_busy)begin
    auto_cycles<=auto_cycles+1'b1;
    case(auto_phase)
     1:if(state==0&&!active&&tail==0&&!replay_busy)begin
      st_sel<=auto_layer==12?31:auto_layer;
      reset_count<=16;
      enqueued<=WIDTH*HEIGHT;consumed<=0;produced<=0;tail<=0;done<=0;active<=0;state<=7;
      run_cycles<=0;first_output_cycles<=0;input_stalls<=0;output_stalls<=0;
      auto_frames<=auto_frames+1'b1;auto_phase<=2;
     end
     2:if(done&&!active&&tail==0&&!replay_busy)begin
      if(auto_layer==12)begin if(video_active)begin video_done<=1;video_ok<=1;video_active<=0;end auto_busy<=0;auto_done<=1;auto_phase<=0;style_ready[style]<=1;rotation[style]<=0;end
      else if(st_done)begin in_start<=1;auto_phase<=3;end
     end
     3:if(in_done)begin
      auto_writes<=auto_writes+in_writes;auto_math_cycles<=auto_math_cycles+in_cycles;
      if(in_error)begin if(video_active)begin video_done<=1;video_ok<=0;video_active<=0;end auto_errors<=auto_errors+1'b1;auto_busy<=0;auto_done<=0;auto_phase<=0;end
      else if(auto_mode)begin
       if(video_active)begin video_done<=1;video_ok<=1;video_active<=0;end
       rotation[style]<=auto_layer==11?0:auto_layer+1'b1;auto_busy<=0;auto_done<=1;auto_phase<=0;
      end else begin auto_layer<=auto_layer+1'b1;auto_phase<=1;end
     end
     default:begin if(video_active)begin video_done<=1;video_ok<=0;video_active<=0;end auto_errors<=auto_errors+1'b1;auto_busy<=0;auto_done<=0;auto_phase<=0;end
    endcase
   end
   if(video_start&&video_idle)begin
    style<=video_style;auto_mode<=video_mode;auto_layer<=video_mode?rotation[video_style]:0;
    auto_busy<=1;auto_done<=0;auto_phase<=1;auto_cycles<=0;auto_frames<=0;auto_writes<=0;auto_math_cycles<=0;auto_errors<=0;
    video_active<=1;video_ok<=0;if(!video_mode)style_ready[video_style]<=0;
   end
  end
 end
endmodule
