// Replay bank 0 once, converting four padded RGB pixels per DDR beat to RGB24.
// Start is accepted only after the prior frame was entirely consumed; no abort.
// Reserve FIFO room for all 16 beats BEFORE ARVALID to avoid blocking HDMI on R.
module sc_replay #(parameter PIXELS=640*480)(
 input uc,urst,input ac,arst,input start,input bank,
 output [23:0] pixel,output valid,input ready,output reg busy,
 output [31:0] errors,
 output reg [31:0] araddr,output reg arvalid,input arready,
 input [127:0] rdata,input rvalid,input rlast,input [1:0] rresp,output rready);
 localparam WORDS=PIXELS/4;
 reg toggle;reg [31:0] pixels_taken,words_taken,words_gray;
 reg [1:0] phase;
 wire [127:0] data;wire fv,fr,fw;
 wire [127:0] shifted=data>>(phase*32);
 assign pixel=shifted[23:0];assign valid=busy&&fv&&!urst;
 assign fr=valid&&ready&&(phase==3);
 always @(posedge uc)begin
  if(urst)begin toggle<=0;busy<=0;phase<=0;pixels_taken<=0;words_taken<=0;words_gray<=0;end
  else begin
   if(start&&!busy)begin toggle<=!toggle;busy<=1;phase<=0;pixels_taken<=0;end
   if(valid&&ready)begin
    phase<=phase+1'b1;pixels_taken<=pixels_taken+1'b1;
    if(phase==3)begin words_taken<=words_taken+1'b1;words_gray<=((words_taken+1'b1)>>1)^(words_taken+1'b1);end
    if(pixels_taken==PIXELS-1)busy<=0;
   end
  end
 end
 (* async_reg="true" *) reg t1,t2,t3;
 (* async_reg="true" *) reg [31:0] g1,g2;
 reg seen,active,inflight,frame_bank;reg [31:0] issued,frame_issued,error_count;
 reg [3:0] beat;reg [31:0] taken_sync;integer j;
 always @*begin
  taken_sync[31]=g2[31];
  for(j=30;j>=0;j=j-1)taken_sync[j]=taken_sync[j+1]^g2[j];
 end
 assign rready=inflight&&fw;
 sc_async_fifo #(.W(128),.AW(6)) fifo(ac,arst,rdata,rvalid&&rready,fw,uc,urst,data,fv,fr,);
 always @(posedge ac)begin
  if(arst)begin
   t1<=0;t2<=0;t3<=0;g1<=0;g2<=0;seen<=0;active<=0;inflight<=0;
   issued<=0;frame_issued<=0;frame_bank<=0;araddr<=0;arvalid<=0;beat<=0;error_count<=0;
  end else begin
   t1<=toggle;t2<=t1;t3<=t2;g1<=words_gray;g2<=g1;
   if(t3!=seen)begin seen<=t3;active<=1;frame_issued<=0;frame_bank<=bank;end
   if(active&&!arvalid&&!inflight&&(issued-taken_sync<=48))begin
    araddr<=(frame_bank?32'h200000:0)+(frame_issued<<4);arvalid<=1;
   end
   if(arvalid&&arready)begin
    arvalid<=0;inflight<=1;beat<=0;issued<=issued+16;frame_issued<=frame_issued+16;
    if(frame_issued==WORDS-16)active<=0;
   end
   if(rvalid&&rready)begin
    beat<=beat+1'b1;
    if(rresp!=0||rlast!=(beat==15))error_count<=error_count+1'b1;
    if(rlast)inflight<=0;
   end
  end
 end
 reg [31:0] e1,e2;always @(posedge uc)begin e1<=error_count;e2<=e1;end
 assign errors=e2;
endmodule
