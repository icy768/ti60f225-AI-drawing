// Bundled-data mailbox between the 100 MHz control and 150 MHz accelerator.
// The sender holds every payload until the return toggle crosses two flops.
// The engine holds completion counters until the next acknowledged command.
// No image storage is added here; replay/upload use their existing async FIFOs.
module sc_engine_cdc #(parameter WIDTH=640,HEIGHT=480,IN_TRACE=0,IN_FILE="model/in_constants.mem")(
 input clk,system_reset,nc,nrst,
 input sink_ready,output [23:0] sink_data,output sink_valid,output new_frame,
 input [23:0] replay_data,input replay_valid,output replay_ready,
 output replay_start,input replay_busy,
 input video_start,input [1:0] video_style,input video_mode,input [1:0] video_bank,
 input [1:0] video_blend_style,input [3:0] video_blend_alpha,
 output video_idle,output reg video_done,video_ok,output reg [2:0] video_styles_ready,
 output reg [1:0] upload_bank,
 input cpu_cfg_we,cpu_cfg_sel,input [4:0] cpu_cfg_lane,cpu_cfg_layer,
 input [11:0] cpu_cfg_addr,input [37:0] cpu_cfg_data,output reg cpu_cfg_rejects,
 output reg [31:0] run_cycles,first_output_cycles,input_stalls,output_stalls,
 output reg [31:0] auto_cycles,auto_frames,auto_writes,auto_errors,errors);
 reg req,ack,pending,command_cfg;reg [60:0] command;
 (* async_reg="true" *)reg ack1,ack2,idle1,idle2;
 (* async_reg="true" *)reg req1,req2;
 reg seen,ack_seen,job_active,cfg_wait;
 reg nstart,ncfg;reg [1:0] nstyle;reg nmode,nsel;reg [1:0] nbstyle;reg [3:0] nbalpha;
 reg [4:0] nlane,nlayer;reg [11:0] naddr;reg [37:0] ndata;
 wire nidle,ndone,nok,nreject;wire [2:0] nstyles;
 wire [31:0] nrun,nfirst,ninput,noutput,nauto,nframes,nwrites,naerrors,nerrors;
 assign video_idle=!pending&&idle2;
 always @(posedge clk)begin
  video_done<=0;
  if(system_reset)begin
   req<=0;pending<=0;command_cfg<=0;command<=0;ack1<=0;ack2<=0;ack_seen<=0;idle1<=0;idle2<=0;
   video_ok<=0;video_styles_ready<=0;cpu_cfg_rejects<=0;
   run_cycles<=0;first_output_cycles<=0;input_stalls<=0;output_stalls<=0;
   auto_cycles<=0;auto_frames<=0;auto_writes<=0;auto_errors<=0;errors<=0;
  end else begin
   ack1<=ack;ack2<=ack1;idle1<=nidle;idle2<=idle1;
   if(ack2!=ack_seen)begin
    ack_seen<=ack2;pending<=0;
    if(nreject)cpu_cfg_rejects<=1;
    if(!command_cfg)begin
     video_done<=1;video_ok<=nok;video_styles_ready<=nstyles;
     run_cycles<=nrun;first_output_cycles<=nfirst;input_stalls<=ninput;output_stalls<=noutput;
     auto_cycles<=nauto;auto_frames<=nframes;auto_writes<=nwrites;auto_errors<=naerrors;errors<=nerrors;
    end
   end
   if(cpu_cfg_we)begin
    if(video_idle)begin
     command_cfg<=1;command<={cpu_cfg_sel,cpu_cfg_lane,cpu_cfg_layer,cpu_cfg_addr,cpu_cfg_data};
     req<=!req;pending<=1;
    end else cpu_cfg_rejects<=1;
   end else if(video_start&&video_idle)begin
    command_cfg<=0;command<={50'd0,video_blend_alpha,video_blend_style,video_bank,video_mode,video_style};req<=!req;pending<=1;
   end
  end
 end
 always @(posedge nc)begin
  nstart<=0;ncfg<=0;
  if(nrst)begin
   req1<=0;req2<=0;seen<=0;ack<=0;job_active<=0;cfg_wait<=0;
   nstyle<=0;nmode<=0;nbstyle<=0;nbalpha<=0;upload_bank<=0;nsel<=0;nlane<=0;nlayer<=0;naddr<=0;ndata<=0;
  end else begin
   req1<=req;req2<=req1;
   // A config write is sampled by sc_engine on this edge, then acknowledged.
   if(cfg_wait)begin ack<=seen;cfg_wait<=0;end
   if(job_active&&ndone)begin ack<=seen;job_active<=0;end
   if(req2!=seen&&nidle&&!cfg_wait&&!job_active)begin
    seen<=req2;
    if(command_cfg)begin
     {nsel,nlane,nlayer,naddr,ndata}<=command;ncfg<=1;cfg_wait<=1;
    end else begin
     {nbalpha,nbstyle,upload_bank,nmode,nstyle}<=command[10:0];nstart<=1;job_active<=1;
    end
   end
  end
 end
 sc_engine #(.WIDTH(WIDTH),.HEIGHT(HEIGHT),.IN_TRACE(IN_TRACE),.IN_FILE(IN_FILE)) fast(
  .clk(nc),.system_reset(nrst),.sink_ready(sink_ready),.sink_data(sink_data),.sink_valid(sink_valid),.new_frame(new_frame),
  .replay_data(replay_data),.replay_valid(replay_valid),.replay_ready(replay_ready),.replay_start(replay_start),.replay_busy(replay_busy),
  .video_start(nstart),.video_style(nstyle),.video_mode(nmode),.video_blend_style(nbstyle),.video_blend_alpha(nbalpha),.video_idle(nidle),.video_done(ndone),.video_ok(nok),.video_styles_ready(nstyles),
  .cpu_cfg_we(ncfg),.cpu_cfg_sel(nsel),.cpu_cfg_lane(nlane),.cpu_cfg_layer(nlayer),.cpu_cfg_addr(naddr),.cpu_cfg_data(ndata),.cpu_cfg_rejects(nreject),
  .run_cycles(nrun),.first_output_cycles(nfirst),.input_stalls(ninput),.output_stalls(noutput),
  .auto_cycles(nauto),.auto_frames(nframes),.auto_writes(nwrites),.auto_errors(naerrors),.errors(nerrors));
endmodule
