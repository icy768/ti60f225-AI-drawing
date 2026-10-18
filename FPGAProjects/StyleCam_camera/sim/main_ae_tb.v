module tb #(parameter IW=96,IH=80,OW=32,OH=24,N=15);
 localparam [23:0] DARK_SUM=64*N, BRIGHT_SUM=255*N;
 localparam [15:0] SAMPLE_COUNT=N,CLIP_LIMIT=(N>>5)+1;
 reg clk=0;always #10 clk=~clk;
 reg rst=1,vs=0,valid=0;reg [39:0] raw=0;
 reg [15:0] gain=256;reg gain_req=0,ae_ack=0;
 wire [55:0] ae_data;wire ae_request;
 wire [47:0] rgb;wire rv,sof,eof;wire [31:0] frames,errors;
 sc_camera_rgb #(.IW(IW),.IH(IH),.OW(OW),.OH(OH)) dut(
  .clk(clk),.rst(rst),.vs(vs),.valid(valid),.raw(raw),
  .rgb(rgb),.rgb_valid(rv),.sof(sof),.eof(eof),.frames(frames),.format_errors(errors),
  .rgb_r_gain(gain),.rgb_g_gain(gain),.rgb_b_gain(gain),.rgb_request(gain_req),.rgb_ack(),
  .ae_data(ae_data),.ae_request(ae_request),.ae_ack(ae_ack));
 task frame(input [9:0] sample);
  integer y,x;
  begin
   valid=0;vs=1;repeat(5)@(negedge clk);vs=0;repeat(5)@(negedge clk);
   for(y=0;y<IH;y=y+1)begin
    for(x=0;x<IW;x=x+4)begin
     valid=1;raw={4{sample}};@(negedge clk);
     if(x%16==0)begin valid=0;repeat(2)@(negedge clk);end
    end
    valid=0;repeat(10)@(negedge clk);
   end
   repeat(20)@(negedge clk);
  end
 endtask
 initial begin
  repeat(5)@(negedge clk);rst=0;
  frame(320);if(ae_request)$fatal(1,"premature snapshot");
  frame(544);
  if(!ae_request||ae_data!=={DARK_SUM,SAMPLE_COUNT,16'd0})$fatal(1,"linear pre-Gamma metering %h",ae_data);
  gain=512;gain_req=1;
  frame(1023);
  if(!ae_request||ae_data!=={DARK_SUM,SAMPLE_COUNT,16'd0})$fatal(1,"snapshot changed before ACK");
  ae_ack=1;repeat(10)@(negedge clk);
  gain=256;gain_req=0;frame(104);
  if(ae_request||ae_data!=={BRIGHT_SUM,SAMPLE_COUNT,CLIP_LIMIT})$fatal(1,"clipping statistics %h",ae_data);
  if(errors)$fatal(1,"metering disturbed input");
  rst=1;repeat(3)@(negedge clk);
  if(ae_request||ae_data)$fatal(1,"metering reset");
  $display("PASS AE %0dx%0d: %0d samples, sparse linear luma/ROI/count/clipping, gaps, held snapshot, ACK, reset",IW,IH,N);
  $finish;
 end
 initial begin #1000000000;$fatal(1,"timeout");end
endmodule
