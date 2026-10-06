// Request: A5 opcode lengthLE16 payload XOR(opcode,length,payload).
// Reply:   5A status lengthLE16 payload XOR(status,length,payload).
// One outstanding transaction. ENQUEUE is atomic after checksum verification.
module StyleCam_uart #(parameter DIV=108, WIDTH=640, HEIGHT=480, N_STYLES=3, FW_VERSION=9, IN_TRACE=1, KEY_CYCLES=1000000, CLOCK_HZ=100000000, IN_FILE="model/in_constants.mem")(
 (* syn_peri_port=0 *) input wire clk_25m,
 (* syn_peri_port=0 *) input wire uart_rx,
 (* syn_peri_port=0 *) output wire uart_tx,
 input system_reset,input style_key_n,input sink_ready, output [23:0] sink_data, output sink_valid,
 output new_frame,output original_frame,output reg [1:0] display_mode,output [1:0] current_style,
 input [255:0] display_status,
 input [23:0] replay_data,input replay_valid,output replay_ready,
 output replay_start,input replay_busy,input [31:0] replay_errors,
 input video_enabled,video_start,input [1:0] video_style,input video_mode,
 output video_idle,output reg video_done,video_ok,output [2:0] video_styles_ready,
 input [255:0] video_status,input [287:0] sensor_diagnostics);
 wire clk=clk_25m;
 reg [9:0] por=0; always @(posedge clk) if(!(&por)) por<=por+1'b1;
 wire rst=!(&por)||system_reset;
 wire key_press,key_released;
 sc_button #(.CYCLES(KEY_CYCLES)) key_filter(clk,rst,style_key_n,key_press,key_released);
 reg key_pending,key_running;
 reg [2:0] style_ready;
 reg [31:0] key_presses,key_switches;
 wire [7:0] rx; wire rv,re,tx_ready,rx_busy; reg [7:0] tx_data; reg tx_valid;
 uart_byte #(.DIV(DIV)) uart(clk,rst,uart_rx,uart_tx,rx,rv,re,tx_data,tx_valid,tx_ready,rx_busy);
 reg [5:0] state; reg [7:0] cmd,check,status; reg [15:0] len,pos;
 reg [7:0] args[0:7]; reg [7:0] reply[0:31];
 reg [23:0] imem[0:255]; reg [15:0] pack;
 reg [1:0] rgb; reg [7:0] iw,ir; reg [8:0] pending; reg accept_packet;
 reg [23:0] iq; reg ifresh;
 always @(posedge clk) iq<=imem[ir];
 reg [23:0] omem[0:511]; reg [8:0] ow,orr;
 reg [9:0] oc; reg [23:0] oq;
 always @(posedge clk) oq<=omem[orr];
 reg pop; wire push;
 reg bypass,local_source; reg [3:0] style; reg capture,active,done;
 assign current_style=style[1:0];
 reg [31:0] run_cycles,first_output_cycles,input_stalls,output_stalls;
 reg [31:0] enqueued,consumed,produced,errors;
 reg [4:0] reset_count,tail,st_sel; reg st_arm,st_fs,st_fe;
 reg [7:0] st_idx; wire [39:0] st_s1; wire [59:0] st_s2; wire st_done,st_busy;
 reg cfg_we; reg [4:0] cfg_layer; reg [11:0] cfg_addr; reg [37:0] cfg_data;
assign video_styles_ready=style_ready;
 reg video_active;
 reg auto_busy,auto_done,auto_mode;reg [2:0] auto_phase;reg [3:0] auto_layer;
 reg [31:0] auto_cycles,auto_frames,auto_writes,auto_math_cycles,auto_errors;
 reg [3:0] rotation[0:2];
 reg in_start;wire in_busy,in_done,in_error,in_cfg_we;wire [7:0] in_idx;
 wire [4:0] in_cfg_layer;wire [11:0] in_cfg_addr;wire [37:0] in_cfg_data,in_trace_data;
 reg [9:0] in_trace_index;wire [31:0] in_cycles,in_writes;
 assign video_idle=state==0&&!rv&&!rx_busy&&!active&&tail==0&&!replay_busy&&!auto_busy&&!in_busy;
 sc_in_refresh #(.WIDTH(WIDTH),.HEIGHT(HEIGHT),.CONSTFILE(IN_FILE),.TRACE(IN_TRACE)) in_update(
 .clk(clk),.rst(rst),.start(in_start),.style(style[1:0]),.layer(auto_layer),
 .busy(in_busy),.done(in_done),.error(in_error),.stats_index(in_idx),.stats_s1(st_s1),.stats_s2(st_s2),
 .cfg_we(in_cfg_we),.cfg_layer(in_cfg_layer),.cfg_addr(in_cfg_addr),.cfg_data(in_cfg_data),
 .trace_index(in_trace_index),.trace_data(in_trace_data),.cycles(in_cycles),.writes(in_writes));
 wire [23:0] nd,net_data; wire nv,net_valid,nready,iready,net_ready;
 wire nrst=rst||(reset_count!=0);
 wire [23:0] input_data=local_source?replay_data:iq;
 wire iv=active&&(local_source?replay_valid:((pending!=0)&&ifresh))&&!nrst;
 assign replay_ready=local_source&&active&&iready&&!nrst;
 assign replay_start=st_fs&&local_source;
 assign nready=(!capture||(oc<512))&&sink_ready;
 assign nd=bypass?input_data:net_data;
 assign nv=bypass?iv:net_valid;
 assign iready=bypass?nready:net_ready;
 assign sink_data=nd; assign sink_valid=nv&&(!capture||(oc<512))&&!nrst;
 assign new_frame=st_fs; assign original_frame=bypass;
 assign push=nv&&nready&&capture&&!nrst;
 wire take=iv&&iready;
 stylenet_top net(.clk(clk),.rst(nrst),.style(style),.cfg_we(cfg_we||in_cfg_we),.cfg_sel(1'b0),
 .cfg_layer(in_cfg_we?in_cfg_layer:cfg_layer),.cfg_lane(5'd0),.cfg_addr(in_cfg_we?in_cfg_addr:cfg_addr),.cfg_data(in_cfg_we?in_cfg_data:cfg_data),
 .i_data(input_data),.i_valid(iv&&!bypass),.i_ready(net_ready),.o_data(net_data),.o_valid(net_valid),.o_ready(nready&&!bypass),
 .st_sel(st_sel),.st_arm(st_arm),.st_fs(st_fs),.st_fe(st_fe),.st_idx(in_busy?in_idx:st_idx),
 .st_s1(st_s1),.st_s2(st_s2),.st_done(st_done),.st_busy(st_busy));
 reg [15:0] rlen,ti; reg [7:0] tch; reg drain;
 reg [8:0] np; reg [3:0] delay_count; integer j;
 // States 0..5 receive, 6 execute, 7 reset wait, 8 cfg/stats wait,
 // 10..13 transmit framing, 14 payload, 15 checksum, 16 idle wait.
 always @(posedge clk) begin
  tx_valid<=0;video_done<=0; pop<=0; cfg_we<=0; st_arm<=0; st_fs<=0; st_fe<=0;in_start<=0;
  if(rst) begin
   state<=0; pending<=0; ir<=0; iw<=0; ifresh<=0; ow<=0; orr<=0; oc<=0;
   reset_count<=0; tail<=0; active<=0; done<=0; capture<=0; style<=0; bypass<=0; display_mode<=0;
   enqueued<=0; consumed<=0; produced<=0; errors<=0; st_sel<=31; st_idx<=0;
   cfg_layer<=0; cfg_addr<=0; cfg_data<=0; rgb<=0; drain<=0;
   local_source<=0;run_cycles<=0;first_output_cycles<=0;input_stalls<=0;output_stalls<=0;
   key_pending<=0;key_running<=0;style_ready<=0;key_presses<=0;key_switches<=0;
   video_active<=0;video_ok<=0;video_done<=0;auto_busy<=0;auto_done<=0;auto_mode<=0;auto_phase<=0;auto_layer<=0;in_trace_index<=0;
   auto_cycles<=0;auto_frames<=0;auto_writes<=0;auto_math_cycles<=0;auto_errors<=0;
   for(j=0;j<3;j=j+1)rotation[j]<=0;
  end else begin
   if(key_press)begin key_pending<=1;key_presses<=key_presses+1'b1;end
   if(re) errors<=errors+1'b1;
   if(reset_count!=0) reset_count<=reset_count-1'b1;
   ifresh<=1;
   if(active&&!nrst)begin
    run_cycles<=run_cycles+1'b1;
    if(iv&&!iready)input_stalls<=input_stalls+1'b1;
    if(nv&&!nready)output_stalls<=output_stalls+1'b1;
   end
   if(take) begin
    consumed<=consumed+1'b1;
    if(!local_source)begin ir<=ir+1'b1;pending<=pending-1'b1;ifresh<=0;end
   end
   if(push) begin omem[ow]<=nd; ow<=ow+1'b1; end
   if(pop) orr<=orr+1'b1;
   case({push,pop}) 2'b10:oc<=oc+1'b1; 2'b01:oc<=oc-1'b1; default:; endcase
   if(nv&&nready&&!nrst) begin
    if(produced==0)first_output_cycles<=run_cycles+1'b1;
    produced<=produced+1'b1;
    if(produced==WIDTH*HEIGHT-1) begin tail<=16; active<=0; end
   end
   if(tail!=0) begin tail<=tail-1'b1; if(tail==1) begin
    st_fe<=1;done<=1;
    if(bypass)style_ready<=0;
    if(key_running&&!auto_busy)begin display_mode<=2;key_running<=0;end
   end end
   case(state)
    0: if(rv&&rx==8'ha5) state<=1;
    1: if(rv) begin cmd<=rx; check<=rx; state<=2; end
    2: if(rv) begin len[7:0]<=rx; check<=check^rx; state<=3; end
    3: if(rv) begin
     len[15:8]<=rx; check<=check^rx; pos<=0; rgb<=0; iw<=0; accept_packet<=(pending==0);
     state<=((rx==0)&&(len[7:0]==0))?5:4;
    end
    4: if(rv) begin
     check<=check^rx;
     if(pos<8) args[pos[2:0]]<=rx;
     if(cmd==3&&accept_packet&&pos<768) begin
      if(rgb==0) pack[7:0]<=rx;
      if(rgb==1) pack[15:8]<=rx;
      if(rgb==2) begin imem[iw]<={rx,pack}; iw<=iw+1'b1; rgb<=0; end
      else rgb<=rgb+1'b1;
     end
     pos<=pos+1'b1;
     if(pos==len-1) state<=5;
    end
    5: if(rv) begin
     rlen<=0; status<=0; drain<=0;
     if(check!=rx) begin status<=1; errors<=errors+1'b1; state<=10; end
     else state<=6;
    end
    6: begin
     state<=10;
     if(video_enabled&&(cmd==2||cmd==3||cmd==4||cmd==6||cmd==8||cmd==10||cmd==12||cmd==14))status<=3;
     else case(cmd)
      1: begin
       rlen<=12;
       reply[0]<=8'h53; reply[1]<=8'h43; reply[2]<=8'h55; reply[3]<=FW_VERSION;
       reply[4]<=WIDTH%256; reply[5]<=WIDTH/256; reply[6]<=HEIGHT%256; reply[7]<=HEIGHT/256;
       reply[8]<=27; reply[9]<=0; reply[10]<=N_STYLES; reply[11]<=13;
      end
      2: if(len==3&&args[0]<N_STYLES&&!active&&tail==0&&!replay_busy&&!auto_busy) begin
       local_source<=0;run_cycles<=0;first_output_cycles<=0;input_stalls<=0;output_stalls<=0;
       style<=args[0][3:0]; st_sel<=args[1][4:0]; capture<=args[2][0]; bypass<=args[2][1]; reset_count<=16;
       pending<=0; ir<=0; ifresh<=0; ow<=0; orr<=0; oc<=0;
       enqueued<=0; consumed<=0; produced<=0; tail<=0; done<=0; active<=0; state<=7;
      end else status<=3;
      3: if(!accept_packet) status<=2;
         else if(len==0||len>768||rgb!=0||!active||local_source||enqueued+(len/3)>WIDTH*HEIGHT) status<=3;
         else begin pending<=len/3; ir<=0; ifresh<=0; enqueued<=enqueued+len/3; end
      4: begin np<=(oc>256)?256:oc; rlen<=((oc>256)?256:oc)*3; drain<=1; rgb<=0; end
      5: begin
       rlen<=24;
       for(j=0;j<4;j=j+1) begin
        reply[j]<=enqueued>>(8*j); reply[4+j]<=consumed>>(8*j);
        reply[8+j]<=produced>>(8*j); reply[12+j]<=errors>>(8*j);
       end
       reply[16]<=pending[7:0]; reply[17]<={7'd0,pending[8]};
       reply[18]<=oc[7:0]; reply[19]<={6'd0,oc[9:8]};
       reply[20]<={4'd0,st_busy,st_done,done,active}; reply[21]<=style; reply[22]<=st_sel; reply[23]<=0;
      end
      6: if(len==8&&!active&&tail==0&&args[0]<13&&!auto_busy) begin
       cfg_layer<=args[0][4:0]; cfg_addr<={args[2][3:0],args[1]};
       cfg_data<={args[7][5:0],args[6],args[5],args[4],args[3]}; cfg_we<=1;
       delay_count<=5; state<=8;
      end else status<=3;
      7: if(len==1&&st_done&&!in_busy) begin st_idx<=args[0]; delay_count<=5; state<=8; end else status<=3;
      8: if(len==1&&args[0]<3) display_mode<=args[0][1:0]; else status<=3;
      9: begin rlen<=32; for(j=0;j<32;j=j+1) reply[j]<=display_status>>(8*j); end
      // Local replay: style, statistics layer (31 disables), capture bit0.
      10:if(len==3&&args[0]<N_STYLES&&!active&&tail==0&&!replay_busy&&!auto_busy&&display_status[2]&&display_status[4])begin
       style<=args[0][3:0];st_sel<=args[1][4:0];capture<=args[2][0];bypass<=0;local_source<=1;reset_count<=16;
       pending<=0;ir<=0;ifresh<=0;ow<=0;orr<=0;oc<=0;
       enqueued<=WIDTH*HEIGHT;consumed<=0;produced<=0;tail<=0;done<=0;active<=0;state<=7;
       run_cycles<=0;first_output_cycles<=0;input_stalls<=0;output_stalls<=0;
      end else status<=3;
      11:begin
       rlen<=24;
       for(j=0;j<4;j=j+1)begin
        reply[j]<=run_cycles>>(8*j);reply[4+j]<=first_output_cycles>>(8*j);
        reply[8+j]<=input_stalls>>(8*j);reply[12+j]<=output_stalls>>(8*j);
        reply[16+j]<=replay_errors>>(8*j);
       end
       reply[20]<={5'd0,replay_busy,local_source,active};reply[21]<=0;reply[22]<=0;reply[23]<=0;
      end
      // Host marks which styles have same-frame coefficients installed.
      12:if(len==1&&args[0]<8&&!active&&tail==0&&!auto_busy)style_ready<=args[0][2:0];else status<=3;
      13:begin
       rlen<=12;reply[0]<=style;reply[1]<={5'd0,style_ready};
       reply[2]<={4'd0,key_released,key_running,key_pending,active};reply[3]<=0;
       for(j=0;j<4;j=j+1)begin reply[4+j]<=key_presses>>(8*j);reply[8+j]<=key_switches>>(8*j);end
      end
      // mode 0: 12 ordered calibration passes + final output. mode 1: one
      // frame + one rotating layer update; coefficients apply next frame.
      14:if(len==2&&args[0]<N_STYLES&&args[1]<2&&!active&&tail==0&&!auto_busy&&!replay_busy&&
           display_status[2]&&display_status[4]&&(args[1]==0||style_ready[args[0]]))begin
       style<=args[0][3:0];auto_mode<=args[1][0];auto_layer<=args[1][0]?rotation[args[0]]:0;
       auto_busy<=1;auto_done<=0;auto_phase<=1;auto_cycles<=0;auto_frames<=0;auto_writes<=0;auto_math_cycles<=0;auto_errors<=0;
       display_mode<=1;if(args[1]==0)style_ready[args[0]]<=0;
      end else status<=3;
      15:begin
       rlen<=32;reply[0]<={5'd0,auto_mode,auto_done,auto_busy};reply[1]<=auto_layer;reply[2]<=style;reply[3]<=auto_phase;
       for(j=0;j<4;j=j+1)begin
        reply[4+j]<=auto_cycles>>(8*j);reply[8+j]<=auto_frames>>(8*j);reply[12+j]<=auto_writes>>(8*j);
        reply[16+j]<=auto_math_cycles>>(8*j);reply[20+j]<=auto_errors>>(8*j);reply[24+j]<=CLOCK_HZ>>(8*j);
       end
       reply[28]<={5'd0,style_ready};reply[29]<=0;reply[30]<=0;reply[31]<=0;
      end
      16:if(IN_TRACE&&len==3&&args[0]<3&&args[1]<12&&args[2]<((args[1]==0||args[1]==11)?16:24)&&!in_busy)begin
       in_trace_index<=args[0]*288+args[1]*24+args[2];delay_count<=5;state<=8;
      end else status<=3;
      17:begin rlen<=32;for(j=0;j<32;j=j+1)reply[j]<=video_status>>(8*j);end
      19:if(len==1&&args[0]<9)begin rlen<=4;for(j=0;j<4;j=j+1)reply[j]<=(sensor_diagnostics>>(args[0]*32))>>(8*j);end else status<=3;
      default:status<=3;
     endcase
    end
    7: if(reset_count==0) begin active<=1; st_arm<=1; st_fs<=1; state<=(key_running||auto_busy)?0:10; end
    8: if(delay_count!=0) delay_count<=delay_count-1'b1;
       else begin
        if(cmd==7) begin
         rlen<=13;
         for(j=0;j<5;j=j+1) reply[j]<=st_s1>>(8*j);
         for(j=0;j<8;j=j+1) reply[j+5]<=st_s2>>(8*j);
        end
        if(cmd==16)begin rlen<=5;for(j=0;j<5;j=j+1)reply[j]<=in_trace_data>>(8*j);end
        state<=10;
       end
    10: if(tx_ready&&!tx_valid) begin tx_data<=8'h5a; tx_valid<=1; state<=11; tch<=status^rlen[7:0]^rlen[15:8]; end
    11: if(tx_ready&&!tx_valid) begin tx_data<=status; tx_valid<=1; state<=12; end
    12: if(tx_ready&&!tx_valid) begin tx_data<=rlen[7:0]; tx_valid<=1; state<=13; end
    13: if(tx_ready&&!tx_valid) begin tx_data<=rlen[15:8]; tx_valid<=1; ti<=0; state<=(rlen==0)?15:14; end
    14: if(tx_ready&&!tx_valid) begin
     tx_valid<=1; ti<=ti+1'b1;
     if(drain) begin
      case(rgb)
       0: begin tx_data<=oq[7:0]; tch<=tch^oq[7:0]; rgb<=1; end
       1: begin tx_data<=oq[15:8]; tch<=tch^oq[15:8]; rgb<=2; end
       2: begin tx_data<=oq[23:16]; tch<=tch^oq[23:16]; rgb<=0; pop<=1; end
      endcase
     end else begin tx_data<=reply[ti[4:0]]; tch<=tch^reply[ti[4:0]]; end
     if(ti==rlen-1) state<=15;
    end
    15: if(tx_ready&&!tx_valid) begin tx_data<=tch; tx_valid<=1; state<=16; end
    16: if(tx_ready&&!tx_valid) state<=0;
    default:state<=0;
   endcase
   // Serialize a physical press with UART requests and frame boundaries.
   // Preserve one pending press while busy, and wait for coefficients + DDR.
   if(auto_busy)begin
    auto_cycles<=auto_cycles+1'b1;
    case(auto_phase)
     1:if(state==0&&!rv&&!rx_busy&&!active&&tail==0&&!replay_busy)begin
      st_sel<=auto_layer==12?31:auto_layer;capture<=0;bypass<=0;local_source<=1;
      reset_count<=16;pending<=0;ir<=0;ifresh<=0;ow<=0;orr<=0;oc<=0;
      enqueued<=WIDTH*HEIGHT;consumed<=0;produced<=0;tail<=0;done<=0;active<=0;state<=7;
      run_cycles<=0;first_output_cycles<=0;input_stalls<=0;output_stalls<=0;
      auto_frames<=auto_frames+1'b1;auto_phase<=2;
     end
     2:if(done&&!active&&tail==0&&!replay_busy)begin
      if(auto_layer==12)begin if(video_active)begin video_done<=1;video_ok<=1;video_active<=0;end auto_busy<=0;auto_done<=1;auto_phase<=0;style_ready[style]<=1;rotation[style]<=0;display_mode<=2;key_running<=0;end
      else if(st_done)begin in_start<=1;auto_phase<=3;end
     end
     3:if(in_done)begin
      auto_writes<=auto_writes+in_writes;auto_math_cycles<=auto_math_cycles+in_cycles;
      if(in_error)begin if(video_active)begin video_done<=1;video_ok<=0;video_active<=0;end auto_errors<=auto_errors+1'b1;auto_busy<=0;auto_done<=0;auto_phase<=0;key_running<=0;end
      else if(auto_mode)begin
       if(video_active)begin video_done<=1;video_ok<=1;video_active<=0;end
       rotation[style]<=auto_layer==11?0:auto_layer+1'b1;auto_busy<=0;auto_done<=1;auto_phase<=0;display_mode<=2;key_running<=0;
      end else begin auto_layer<=auto_layer+1'b1;auto_phase<=1;end
     end
     default:begin if(video_active)begin video_done<=1;video_ok<=0;video_active<=0;end auto_errors<=auto_errors+1'b1;auto_busy<=0;auto_done<=0;auto_phase<=0;key_running<=0;end
    endcase
   end
   if(video_enabled&&video_start&&video_idle)begin
    style<=video_style;auto_mode<=video_mode;auto_layer<=video_mode?rotation[video_style]:0;
    auto_busy<=1;auto_done<=0;auto_phase<=1;auto_cycles<=0;auto_frames<=0;auto_writes<=0;auto_math_cycles<=0;auto_errors<=0;
    video_active<=1;video_ok<=0;if(!video_mode)style_ready[video_style]<=0;
   end
   if(!video_enabled&&key_pending&&state==0&&!rv&&!rx_busy&&!active&&tail==0&&!replay_busy&&!auto_busy&&
      display_status[2]&&display_status[4])begin
    key_pending<=key_press;key_running<=1;key_switches<=key_switches+1'b1;
    style<=(style==N_STYLES-1)?0:style+1'b1;st_sel<=31;capture<=0;bypass<=0;local_source<=1;
    reset_count<=16;pending<=0;ir<=0;ifresh<=0;ow<=0;orr<=0;oc<=0;
    enqueued<=WIDTH*HEIGHT;consumed<=0;produced<=0;tail<=0;done<=0;active<=0;state<=7;
    run_cycles<=0;first_output_cycles<=0;input_stalls<=0;output_stalls<=0;
    display_mode<=1;
    if(!style_ready[(style==N_STYLES-1)?0:style+1])begin
     auto_busy<=1;auto_done<=0;auto_mode<=0;auto_layer<=0;auto_phase<=1;
     auto_cycles<=0;auto_frames<=0;auto_writes<=0;auto_math_cycles<=0;auto_errors<=0;state<=0;
    end
   end
  end
 end
endmodule
