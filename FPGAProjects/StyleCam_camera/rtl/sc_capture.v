// Three input frame banks at 0, 0x200000 and 0x800000. Publish only after the final AXI B.
// READY, LOCKED (network) and HELD (original shown on HDMI) banks are never overwritten.
// A full camera frame is skipped if no bank is free. Missing FIFO packets cannot publish a partial frame.
// Only the newest complete frame stays READY. Hold: when a network output is published its input bank
// becomes PENDING; when HDMI confirms the new frame, PENDING becomes DISPLAYED and the old one is freed.
// H_MIRROR reverses each RGB row in DDR: reverse four pixel lanes and
// visit 128-bit words from right to left. No extra image RAM is required.
module sc_capture #(parameter PIXELS=640*480,FIFO_AW=9,WIDTH=640,H_MIRROR=0)(
 input cc,crst,input [47:0] rgb,input cv,sof,eof,
 input ac,arst,calibrated,input take_frame,release_frame,input hold_publish,hold_swap,
 output frame_ready,output [1:0] ready_bank,output reg locked,output reg [1:0] locked_bank,
 output reg [31:0] completed,skipped,errors,output [31:0] overflow,
 output [31:0] awaddr,output awvalid,input awready,
 output [127:0] wdata,output wvalid,input wready,input bvalid,input [1:0] bresp,output bready);
 function [31:0] in_base(input [1:0] b);begin in_base=(b==0)?32'h0:(b==1)?32'h200000:32'h800000;end endfunction
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
 reg [2:0] ready_mask;reg [1:0] ws,bank,pend_bank,disp_bank;reg pend_valid,disp_valid;
 reg capturing,phase,bad,last_word;
 localparam ROW_WORDS=WIDTH/4;
 localparam ROW_W=(ROW_WORDS>1)?$clog2(ROW_WORDS):1;
 localparam INDEX_W=$clog2(PIXELS/4+(H_MIRROR?ROW_WORDS:1));
 reg [31:0] groups,addr;reg [INDEX_W-1:0] word_index;
 reg [ROW_W-1:0] row_word;
 reg [63:0] half;reg [127:0] data;
 assign frame_ready=(|ready_mask)&&!locked;
 assign ready_bank=ready_mask[0]?2'd0:ready_mask[1]?2'd1:2'd2;
 wire taking=take_frame&&frame_ready;
 // A bank is owned while READY, LOCKED by the network, PENDING/DISPLAYED on HDMI, or being taken now.
 wire [2:0] owned=ready_mask|({3{locked}}&(3'b001<<locked_bank))|({3{pend_valid}}&(3'b001<<pend_bank))|
  ({3{disp_valid}}&(3'b001<<disp_bank))|({3{taking}}&(3'b001<<ready_bank));
 wire free0=!owned[0],free1=!owned[1],free2=!owned[2];
 assign fr=ws==0&&calibrated&&!arst;
 assign awaddr=addr;assign awvalid=ws==1;assign wdata=data;assign wvalid=ws==2;assign bready=ws==3;
 always @(posedge ac)begin
  if(arst)begin ready_mask<=0;ws<=0;capturing<=0;phase<=0;bad<=0;groups<=0;word_index<=0;row_word<=0;locked<=0;locked_bank<=0;completed<=0;skipped<=0;errors<=0;bank<=0;last_word<=0;addr<=0;data<=0;half<=0;
   pend_valid<=0;pend_bank<=0;disp_valid<=0;disp_bank<=0;end
  else begin
   if(release_frame)begin locked<=0;if(hold_publish)begin pend_valid<=1;pend_bank<=locked_bank;end end
   if(hold_swap&&pend_valid)begin disp_valid<=1;disp_bank<=pend_bank;pend_valid<=0;end
   if(taking)begin locked<=1;locked_bank<=ready_bank;ready_mask[ready_bank]<=0;end
   case(ws)
    0:if(fv&&fr)begin
     if(fd[48])begin
      if(capturing)errors<=errors+1'b1;
      phase<=1;groups<=1;word_index<=H_MIRROR?ROW_WORDS-1:0;row_word<=0;bad<=0;
      half<={8'd0,fd[47:24],8'd0,fd[23:0]};
      if(free0||free1||free2)begin capturing<=1;bank<=free0?2'd0:free1?2'd1:2'd2;end
      else begin capturing<=0;skipped<=skipped+1'b1;end
     end else if(capturing)begin
      groups<=groups+1'b1;
      if(!phase)begin half<={8'd0,fd[47:24],8'd0,fd[23:0]};phase<=1;
       if(fd[49])begin capturing<=0;errors<=errors+1'b1;end
      end else begin
       phase<=0;
       data<=H_MIRROR?{half[31:0],half[63:32],8'd0,fd[23:0],8'd0,fd[47:24]}:
                      {8'd0,fd[47:24],8'd0,fd[23:0],half};
       addr<=in_base(bank)+(word_index<<4);ws<=1;
       if(H_MIRROR)begin
        // End of row: advance to the rightmost word of the next row.
        if(row_word==ROW_WORDS-1)begin
         row_word<=0;word_index<=word_index+2*ROW_WORDS-1;
        end else begin row_word<=row_word+1'b1;word_index<=word_index-1'b1;end
       end else word_index<=word_index+1'b1;
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
      // newest frame only: an older READY frame (never locked) is dropped
      if(!bad&&bresp==0)begin ready_mask<=3'b001<<bank;completed<=completed+1'b1;end
      else if(bresp==0)errors<=errors+1'b1;
     end
    end
   endcase
  end
 end
endmodule
