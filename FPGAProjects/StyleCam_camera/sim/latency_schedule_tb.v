`timescale 1ns/1ps
// Reduced image, real capture/scheduler RTL. 1000 control ticks represent 1 ms.
// The behavioral accelerator is a bounded-service assumption, NOT measured FPS.
module tb;
 parameter SERVICE=32000, VPHASE=11000, FRAMES=100, PAIR_GAP=1160;
 localparam PERIOD=33334, VPERIOD=16667;
 reg clk=0,cc=0;always #5 clk=~clk;always #7 cc=~cc;
 reg rst=1,cv=0,sof=0,eof=0;reg [47:0] rgb=0;reg [1:0] request=0;
 wire ready,locked,take,release_f,swap,start,publish,mode;
 wire [1:0] rb,lb,ib,ob,pb,style,requested,scan_style;
 wire [31:0] completed,skipped,cap_errors,overflow,processed,errors,scan_seq;
 wire [31:0] awaddr;wire av,wv,br;wire [127:0] wd;
 reg ar=0,wr=0,bv=0;reg [1:0] bus=0;reg [31:0] addr;
 integer cycle=0,delay_b=0,remain=0,drain=0,started=0,shown=0;
 reg idle=1,done=0,complete=0,shown_valid=0;reg [1:0] shown_bank=0;
 reg [127:0] memory[0:47];integer bank_frame[0:3];
 integer pending_frame=0;reg pending_display=0;reg [1:0] display_target;
 integer request_at=0,next_request=100000,requests=0,observed=0,max_latency=0;
 reg request_wait=0;integer i,k,b,f,p,target;
 reg [3:0] visited=0;
 function integer bank_of(input [31:0] a);
  begin bank_of=(a>=32'hc00000)?3:(a>=32'h800000)?2:(a>=32'h200000)?1:0;end
 endfunction
 sc_capture #(.PIXELS(48),.WIDTH(12),.FIFO_AW(6)) cap(
  cc,rst,rgb,cv,sof,eof,clk,rst,1'b1,take,release_f,publish,swap,
  ready,rb,locked,lb,completed,skipped,cap_errors,overflow,
  awaddr,av,ar,wd,wv,wr,bv,2'b0,br);
 sc_video_schedule schedule(.clk(clk),.rst(rst),.run(1'b1),.step(1'b0),.style_req(request),
  .frame_ready(ready),.ready_bank(rb),.take_frame(take),.release_frame(release_f),.input_bank(ib),.hold_swap(swap),
  .engine_idle(idle),.engine_done(done),.engine_ok(1'b1),.styles_ready(3'b111),
  .engine_start(start),.engine_style(style),.engine_mode(mode),.output_complete(complete),
  .shown_valid(shown_valid),.shown_bank(shown_bank),.output_bank(ob),.publish(publish),.publish_bank(pb),
  .requested_style(requested),.processed(processed),.errors(errors),.state_status(),
  .clock_cycles(),.scan_sequence(scan_seq),.scan_timestamp(),.publish_wait_cycles(),.scan_style(scan_style));
 always @(posedge clk)begin
  done<=0;
  if(!rst)begin
   cycle<=cycle+1;
   ar<=bus==0&&(cycle%7!=0);wr<=bus==1&&(cycle%5!=0);
   if(av&&ar)begin
    b=bank_of(awaddr);addr<=awaddr;bus<=1;ar<=0;visited[b]<=1;
    if((locked&&lb==b)||(cap.pend_valid&&cap.pend_bank==b)||(cap.disp_valid&&cap.disp_bank==b))
     $fatal(1,"Overwrote owned input bank %0d",b);
   end
   if(wv&&wr)begin
    memory[bank_of(addr)*12+addr[19:4]]<=wd;bus<=2;wr<=0;delay_b<=cycle%23+1;
    if(addr[19:4]==0)bank_frame[bank_of(addr)]<=wd[31:0]/1000;
   end
   if(bus==2&&!bv)begin if(delay_b==0)bv<=1;else delay_b<=delay_b-1;end
   if(bv&&br)begin bv<=0;bus<=0;end
   if(start)begin
    if(!idle||!mode||bank_frame[ib]!=started)$fatal(1,"Lost/reordered frame at inference %0d bank=%0d",started,ib);
    for(i=0;i<12;i=i+1)for(k=0;k<4;k=k+1)
     if(memory[ib*12+i][k*32+:32]!==32'(started*1000+i*4+k))$fatal(1,"Input image corruption");
    started<=started+1;idle<=0;complete<=0;remain<=SERVICE;
    if(shown_valid&&ob==shown_bank)$fatal(1,"Output front overwrite");
   end
   if(!idle)begin
    if(remain==0)begin idle<=1;done<=1;drain<=40;end else remain<=remain-1;
   end
   if(drain!=0)begin drain<=drain-1;if(drain==1)complete<=1;end
   if(publish)begin
    if(pending_display||!complete)$fatal(1,"Premature publication");
    pending_display<=1;display_target<=pb;pending_frame<=bank_frame[ib];
   end
   if(cycle%VPERIOD==VPHASE&&pending_display)begin
    if(pending_frame!=shown)$fatal(1,"Skipped/reordered displayed frame");
    shown<=shown+1;shown_valid<=1;shown_bank<=display_target;pending_display<=0;
   end
   if(cycle==next_request&&started<FRAMES-4)begin
    if(request_wait)$fatal(1,"Prior switch unfinished");
    request<=request==2?0:request+1;request_at<=cycle;request_wait<=1;requests<=requests+1;
    next_request<=next_request+4*PERIOD+7001;
   end
   if(request_wait&&scan_style==request)begin
    if(cycle-request_at>=100000)$fatal(1,"Switch exceeded 100 ms: %0d ticks",cycle-request_at);
    if(cycle-request_at>max_latency)max_latency<=cycle-request_at;
    observed<=observed+1;request_wait<=0;
   end
   if(skipped||cap_errors||overflow||errors)$fatal(1,"Frame loss/errors skip=%0d cap=%0d ov=%0d sch=%0d",skipped,cap_errors,overflow,errors);
  end
 end
 initial begin
  repeat(10)@(negedge clk);rst=0;
  for(f=0;f<FRAMES;f=f+1)begin
   for(p=0;p<24;p=p+1)begin
    target=f*PERIOD+p*PAIR_GAP+100;
    wait(cycle>=target);@(negedge cc);
    rgb={24'(f*1000+p*2+1),24'(f*1000+p*2)};cv=1;sof=p==0;eof=p==23;
    @(negedge cc);cv=0;sof=0;eof=0;
   end
  end
  wait(shown==FRAMES);repeat(20)@(negedge clk);
  if(completed!=FRAMES||processed!=FRAMES||scan_seq!=FRAMES||observed!=requests||requests<10||(visited!=7&&visited!=15))
   $fatal(1,"Incomplete coverage completed=%0d processed=%0d scan=%0d requests=%0d observed=%0d banks=%h",completed,processed,scan_seq,requests,observed,visited);
  $display("PASS bounded scheduler frames=%0d service_ticks=%0d hdmi_phase=%0d skipped=%0d requests=%0d max_switch_ticks=%0d banks=%h",FRAMES,SERVICE,VPHASE,skipped,requests,max_latency,visited);$finish;
 end
 initial begin #50000000;$fatal(1,"Scheduler timeout");end
endmodule
