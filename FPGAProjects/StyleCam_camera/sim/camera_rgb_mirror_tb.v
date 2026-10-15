module tb;
 parameter IW=24, IH=20, OW=8, OH=6, NFRAMES=7;
 localparam PAIRS=OW*OH/2, TOTAL=(NFRAMES+1)*PAIRS;
 reg clk=0; always #10 clk=~clk;
 reg ac=0;always #5 ac=~ac;
 reg rst=1, vs=0, valid=0; reg [39:0] raw=0;
 wire [47:0] rgb; wire v, sof, eof; wire [31:0] frames, errors;
 reg [47:0] expected[0:TOTAL-1];
 reg [2047:0] expected_file;
 integer count=0, f, y, x, k;
 reg [15:0] gain_r=256,gain_g=256,gain_b=256;
 reg gain_req=0,update_gains=0; wire gain_ack;
 sc_camera_rgb #(.IW(IW),.IH(IH),.OW(OW),.OH(OH)) dut
  (.clk(clk),.rst(rst),.vs(vs),.valid(valid),.raw(raw),.rgb(rgb),.rgb_valid(v),.sof(sof),.eof(eof),
   .frames(frames),.format_errors(errors),.rgb_r_gain(gain_r),.rgb_g_gain(gain_g),
   .rgb_b_gain(gain_b),.rgb_request(gain_req),.rgb_ack(gain_ack));

 wire [31:0] awaddr,done,skipped,caperrors,overflow;
 wire awvalid,wvalid,bready,ready,locked;wire [1:0] rb,lb;wire [127:0] wdata;
 reg bvalid=0;reg [31:0] held_addr=0;integer writes=0,wi,expected_addr;
 reg [127:0] expected_word;
 sc_capture #(.PIXELS(OW*OH),.WIDTH(OW),.H_MIRROR(1)) capture
  (.cc(clk),.crst(rst),.rgb(rgb),.cv(v),.sof(sof),.eof(eof),.ac(ac),.arst(rst),
   .calibrated(1'b1),.take_frame(1'b0),.release_frame(1'b0),.hold_publish(1'b0),.hold_swap(1'b0),
   .frame_ready(ready),.ready_bank(rb),.locked(locked),.locked_bank(lb),
   .completed(done),.skipped(skipped),.errors(caperrors),.overflow(overflow),
   .awaddr(awaddr),.awvalid(awvalid),.awready(1'b1),.wdata(wdata),.wvalid(wvalid),
   .wready(1'b1),.bvalid(bvalid),.bresp(2'b0),.bready(bready));
 always @(posedge ac)begin
  if(rst)begin bvalid<=0;held_addr<=0;end
  else begin
   if(awvalid)held_addr<=awaddr;
   if(wvalid)begin
    if(writes>=TOTAL/2)$fatal(1,"extra DDR RGB word");
    wi=writes%(OW*OH/4);
    expected_addr=((wi/(OW/4))*(OW/4)+(OW/4-1-wi%(OW/4)))*16;
    if((held_addr&32'h001fffff)!==expected_addr)$fatal(1,"DDR row address word %0d actual %h expected %h",writes,held_addr,expected_addr);
    expected_word={8'd0,expected[writes*2][23:0],8'd0,expected[writes*2][47:24],
                   8'd0,expected[writes*2+1][23:0],8'd0,expected[writes*2+1][47:24]};
    if(wdata!==expected_word)$fatal(1,"DDR mirrored pixel lanes word %0d actual %h expected %h",writes,wdata,expected_word);
    writes=writes+1;bvalid<=1;
   end
   if(bvalid&&bready)bvalid<=0;
  end
 end

 task next_gains(input integer frame);
  begin
   case((frame+1)%7)
    0:begin gain_r=256;gain_g=256;gain_b=256;end
    1:begin gain_r=512;gain_g=241;gain_b=128;end
    2:begin gain_r=256;gain_g=256;gain_b=256;end
    3:begin gain_r=0;gain_g=256;gain_b=65535;end
    4:begin gain_r=128;gain_g=128;gain_b=128;end
    5:begin gain_r=0;gain_g=0;gain_b=0;end
    6:begin gain_r=256;gain_g=256;gain_b=256;end
   endcase
   gain_req=!gain_req;
  end
 endtask
 function [9:0] sample(input integer frame, input integer xx, input integer yy);
  integer sx, value;
  begin
   sx=xx;
   case(frame)
    0: value=((sx*7+yy*11)%240+16)*4+((xx+yy)%4);
    1: value=(yy%2)?((xx%2)?704:448):((xx%2)?448:256);
    2: value=((sx/3+yy/3)%2)?1023:64;
    3: value=(sx*73+yy*151+sx*yy*19+(sx^yy)*7+frame*31)%1024;
    4: value=(sx*3+yy*5)%80;
    5: value=1023;
    default: begin
     if(yy%2) value=(xx%2)?(12+(sx*5+yy*3)%220):(28+(sx*3+yy*2)%200);
     else value=(xx%2)?(28+(sx*3+yy*2)%200):(8+(sx*2+yy*7)%220);
     value=(value+16)*4;
    end
   endcase
   sample=value;
  end
 endfunction
 always @(posedge clk) if(v) begin
  if(count>=TOTAL) $fatal(1,"unexpected extra RGB pair");
  if(rgb!==expected[count]) $fatal(1,"RGB pair %0d actual %h expected %h",count,rgb,expected[count]);
  if(sof!==(count%PAIRS==0)||eof!==(count%PAIRS==PAIRS-1)) $fatal(1,"RGB frame markers at %0d",count);
  count=count+1;
 end
 task start_frame;
  begin
   valid=0; vs=1; repeat(3) @(negedge clk);
   vs=0; repeat(3) @(negedge clk);
  end
 endtask
 task send_rows(input integer frame, input integer rows);
  integer yy, xx, kk; reg old_ack;
  begin
   for(yy=0;yy<rows;yy=yy+1) begin
    for(xx=0;xx<IW;xx=xx+4) begin
     valid=1;
     for(kk=0;kk<4;kk=kk+1) raw[kk*10+:10]=sample(frame,xx+kk,yy);
     @(negedge clk);
     if(update_gains&&yy==IH/2&&xx==(IW/8)*4) begin
      old_ack=gain_ack; next_gains(frame);
     end
     if(update_gains&&yy>=IH/2&&xx>(IW/8)*4&&gain_ack!==old_ack)
      $fatal(1,"gain changed before next frame boundary");
     if(frame%2==0&&xx%12==0) begin valid=0; repeat(2) @(negedge clk); end
    end
    if(frame%2==0) begin valid=0; repeat(7) @(negedge clk); end
   end
   valid=0; repeat(12) @(negedge clk);
  end
 endtask
 initial begin
  if(!$value$plusargs("EXPECTED=%s",expected_file)) expected_file="validation/camera_sim/rgb_expected.hex";
  $readmemh(expected_file,expected);
  repeat(5) @(negedge clk); rst=0;
  // Abort above the ROI: the next frame must count the bad input length and
  // completely replace old line-buffer contents before any RGB is emitted.
  start_frame; send_rows(3,3);
  update_gains=1;
  for(f=0;f<NFRAMES;f=f+1) begin start_frame; send_rows(f,IH); end
  if(count!=NFRAMES*PAIRS||frames!=NFRAMES+1||errors!=1)
   $fatal(1,"counts %0d frames %0d errors %0d",count,frames,errors);
  wait(done==NFRAMES);
  if(caperrors||overflow||skipped)$fatal(1,"capture before reset");
  // Reset with an unfinished input beat and buffered history.
  update_gains=0;gain_req=0;gain_r=256;gain_g=256;gain_b=256;
  valid=1; rst=1; repeat(3) @(negedge clk); valid=0;
  if(v||sof||eof||frames||errors) $fatal(1,"camera reset");
  rst=0; start_frame; send_rows(1,IH);
  if(count!=TOTAL||frames!=1||errors!=0) $fatal(1,"post-reset frame");
  $display("PASS camera RGB gains + 5x5 MHC: %0d RGB pixels, native BGGR, frame-atomic CDC gain commits, unity/independent/reference zero/full 16-bit gains, crop halo, Gamma, clipping, gaps, frame markers, malformed input and reset",count*2);
  wait(done==1);
  if(writes!=TOTAL/2||caperrors||overflow||skipped)$fatal(1,"capture final counts");
  $display("PASS native BGGR -> RGB -> mirrored DDR: %0d pixels; descending words and reversed lanes, intact rows and channels",writes*4);
  $finish;
 end
 initial begin #1000000000; $fatal(1,"preprocessor timeout"); end
endmodule
