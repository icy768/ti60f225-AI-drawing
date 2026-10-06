// Two input frame banks at 0 and 0x200000. Publish only after the final AXI B.
// READY and LOCKED banks are never overwritten. A full camera frame is skipped
// if both banks are owned. Missing FIFO packets cannot publish a partial frame.
module sc_capture #(parameter PIXELS=640*480,FIFO_AW=9)(
 input cc,crst,input [47:0] rgb,input cv,sof,eof,
 input ac,arst,calibrated,input take_frame,release_frame,
 output frame_ready,output ready_bank,output reg locked,output reg locked_bank,
 output reg [31:0] completed,skipped,errors,output [31:0] overflow,
 output [31:0] awaddr,output awvalid,input awready,
 output [127:0] wdata,output wvalid,input wready,input bvalid,input [1:0] bresp,output bready);
 wire fw,fv,fr;wire [49:0] fd;
 reg [31:0] over_count,over_gray;
 always @(posedge cc)begin
  if(crst)begin over_count<=0;over_gray<=0;end
  else if(cv&&!fw)begin over_count<=over_count+1'b1;over_gray<=((over_count+1'b1)>>1)^(over_count+1'b1);end
 end
 (* async_reg="true" *)reg [31:0] og1,og2;
 reg [31:0] over_sync;integer j;
 always @(posedge ac)begin if(arst)begin og1<=0;og2<=0;end else begin og1<=over_gray;og2<=og1;end end
 always @*begin over_sync[31]=og2[31];for(j=30;j>=0;j=j-1)over_sync[j]=over_sync[j+1]^og2[j];end
 assign overflow=over_sync;
 sc_async_fifo #(.W(50),.AW(FIFO_AW)) fifo(cc,crst,{eof,sof,rgb},cv,fw,ac,arst,fd,fv,fr,);
 reg [1:0] ready_mask,ws;reg capturing,bank,phase,bad,last_word;
 reg [31:0] groups,word_index,addr;reg [63:0] half;reg [127:0] data;
 assign frame_ready=(|ready_mask)&&!locked;
 assign ready_bank=!ready_mask[0];
 wire taking=take_frame&&frame_ready;
 wire free0=!ready_mask[0]&&!(locked&&!locked_bank)&&!(taking&&!ready_bank);
 wire free1=!ready_mask[1]&&!(locked&&locked_bank)&&!(taking&&ready_bank);
 assign fr=ws==0&&calibrated&&!arst;
 assign awaddr=addr;assign awvalid=ws==1;assign wdata=data;assign wvalid=ws==2;assign bready=ws==3;
 always @(posedge ac)begin
  if(arst)begin ready_mask<=0;ws<=0;capturing<=0;phase<=0;bad<=0;groups<=0;word_index<=0;locked<=0;locked_bank<=0;completed<=0;skipped<=0;errors<=0;bank<=0;last_word<=0;addr<=0;data<=0;half<=0;end
  else begin
   if(release_frame)locked<=0;
   if(taking)begin locked<=1;locked_bank<=ready_bank;ready_mask[ready_bank]<=0;end
   case(ws)
    0:if(fv&&fr)begin
     if(fd[48])begin
      if(capturing)errors<=errors+1'b1;
      phase<=1;groups<=1;word_index<=0;bad<=0;
      half<={8'd0,fd[47:24],8'd0,fd[23:0]};
      if(free0||free1)begin capturing<=1;bank<=!free0;end
      else begin capturing<=0;skipped<=skipped+1'b1;end
     end else if(capturing)begin
      groups<=groups+1'b1;
      if(!phase)begin half<={8'd0,fd[47:24],8'd0,fd[23:0]};phase<=1;
       if(fd[49])begin capturing<=0;errors<=errors+1'b1;end
      end else begin
       phase<=0;data<={8'd0,fd[47:24],8'd0,fd[23:0],half};addr<=(bank?32'h200000:0)+(word_index<<4);word_index<=word_index+1'b1;ws<=1;
       last_word<=fd[49];
       if(groups>=PIXELS/2||word_index>=PIXELS/4)begin ws<=0;capturing<=0;errors<=errors+1'b1;end
       else if(fd[49]&&groups!=PIXELS/2-1)bad<=1;
      end
     end
    end
    1:if(awready)ws<=2;
    2:if(wready)ws<=3;
    3:if(bvalid)begin
     ws<=0;
     if(bresp!=0)begin bad<=1;errors<=errors+1'b1;end
     if(last_word)begin
      capturing<=0;
      if(!bad&&bresp==0)begin ready_mask[bank]<=1;completed<=completed+1'b1;end
      else if(bresp==0)errors<=errors+1'b1;
     end
    end
   endcase
  end
 end
endmodule
