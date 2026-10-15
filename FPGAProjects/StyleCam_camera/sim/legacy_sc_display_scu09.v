// Two 640x480 RGB frame stores in DDR; 2x nearest-neighbour display in 1080p60.
module sc_display_scu09 #(parameter IW=640,IH=480)(
 input uc,input urst,input ac,input arst,input pc,input prst,input calibrated,
 input [23:0] pixel,input pv,output pready,input new_frame,input original_frame,
 input [1:0] mode,output [255:0] status,
 input write_bank,publish,publish_bank,output output_complete,output shown_valid,shown_bank,
 output [31:0] awaddr,output awvalid,input awready,
 output [127:0] wdata,output wvalid,input wready,input bvalid,input [1:0] bresp,output bready,
 output [31:0] araddr,output arvalid,input arready,
 input [127:0] rdata,input rvalid,input rlast,input [1:0] rresp,output rready,
 output reg hs,vs,de,output reg [7:0] red,green,blue);
 localparam WORDS=IW*IH/4,COLS=IW/64;
 reg cal1,cal2; always @(posedge uc) begin cal1<=calibrated;cal2<=cal1;end
 reg [1:0] pack_phase; reg [95:0] pack_data; reg [16:0] word_index;
 wire wf_ready,wf_valid,wf_take; wire [147:0] wf_data;
 wire [147:0] packed_word={word_index==WORDS-1,word_index==0,write_bank,word_index,8'd0,pixel,pack_data};
 assign pready=cal2&&!urst&&((pack_phase!=3)||wf_ready);
 wire pack_fire=pv&&pready;
 always @(posedge uc) begin
  if(urst||new_frame) begin pack_phase<=0;word_index<=0;end
  else if(pack_fire) begin
   pack_phase<=pack_phase+1'b1;
   case(pack_phase)
    0:pack_data[31:0]<={8'd0,pixel};
    1:pack_data[63:32]<={8'd0,pixel};
    2:pack_data[95:64]<={8'd0,pixel};
    3:word_index<=word_index+1'b1;
   endcase
  end
 end
 sc_async_fifo #(.W(148),.AW(6)) upload_fifo(uc,urst,packed_word,pack_fire&&(pack_phase==3),wf_ready,
  ac,arst,wf_data,wf_valid,wf_take,);
 reg [1:0] ws;reg [127:0] wr_data;reg [31:0] wr_addr;
 reg wr_last,wr_bank,frame_write_error;reg [1:0] valid_banks;reg [31:0] write_words,write_errors,read_errors;
 assign wf_take=(ws==0)&&calibrated&&!arst;
 assign awaddr=wr_addr;assign awvalid=ws==1;
 assign wdata=wr_data;assign wvalid=ws==2;assign bready=ws==3;
 always @(posedge ac) begin
  if(arst) begin ws<=0;frame_write_error<=0;valid_banks<=0;write_words<=0;write_errors<=0;end
  else case(ws)
   0:if(wf_valid&&wf_take) begin
    wr_data<=wf_data[127:0];wr_addr<=32'h400000+{10'd0,wf_data[145],wf_data[144:128],4'd0};
    wr_last<=wf_data[147];wr_bank<=wf_data[145];ws<=1;
    if(wf_data[146]) begin valid_banks[wf_data[145]]<=0;write_words<=0;frame_write_error<=0;end
   end
   1:if(awready) ws<=2;
   2:if(wready) ws<=3;
   3:if(bvalid) begin
    ws<=0;write_words<=write_words+1'b1;
    if(bresp!=0)begin frame_write_error<=1;write_errors<=write_errors+1'b1;end
    if(wr_last&&bresp==0&&!frame_write_error)valid_banks[wr_bank]<=1;
   end
  endcase
 end
 assign output_complete=(write_words==WORDS)&&(ws==0)&&!wf_valid&&valid_banks[write_bank];
 reg published_valid,published_bank;
 always @(posedge ac)begin
  if(arst)begin published_valid<=0;published_bank<=0;end
  else if(publish)begin published_valid<=1;published_bank<=publish_bank;end
 end
 (* async_reg="true" *) reg pubv1,pubv2,pubb1,pubb2;
 always @(posedge pc)begin
  if(prst)begin pubv1<=0;pubv2<=0;pubb1<=0;pubb2<=0;end
  else begin pubv1<=published_valid;pubv2<=pubv1;pubb1<=published_bank;pubb2<=pubb1;end
 end
 // Request a fresh DDR scan during vertical blank; this also recovers alignment after underflow.
 reg [11:0] x,y;reg request_toggle,request_bank,request_enable;
 reg image_enable;reg [1:0] shown_mode;
 (* async_reg="true" *) reg [1:0] mode1,mode2,banks1,banks2;
 reg [31:0] video_frames,underflow,last_underflow;reg underflow_seen;
 wire inside_image=(x>=320)&&(x<320+IW*2)&&(y>=60)&&(y<60+IH*2);
 wire rf_valid,rf_take,rf_ready;wire [95:0] rf_data;
 wire [9:0] rf_level;
 reg [5:0] flush_count;wire flush=(flush_count!=0);
 (* async_reg="true" *) reg flush1,flush2;
 wire pf_reset=prst||flush2;
 assign rf_take=image_enable&&inside_image&&(x[2:0]==7)&&!pf_reset;
 wire [23:0] selected_pixel=rf_data>>(x[2:1]*24);
 reg [23:0] color;
 always @* begin
  if(x<240)color=24'hffffff;else if(x<480)color=24'hffff00;
  else if(x<720)color=24'h00ffff;else if(x<960)color=24'h00ff00;
  else if(x<1200)color=24'hff00ff;else if(x<1440)color=24'hff0000;
  else if(x<1680)color=24'h0000ff;else color=24'h202020;
  if(image_enable) begin
   color=24'h101010;
   if((x>=316)&&(x<320+IW*2+4)&&(y>=56)&&(y<60+IH*2+4)) color=(shown_mode==1)?24'h20c060:24'h4080ff;
   if(inside_image)color=rf_valid?{selected_pixel[7:0],selected_pixel[15:8],selected_pixel[23:16]}:24'hff00ff;
  end
 end
 always @(posedge pc) begin
  mode1<=mode;mode2<=mode1;banks1<=valid_banks;banks2<=banks1;flush1<=flush;flush2<=flush1;
  if(prst) begin
   x<=0;y<=0;request_toggle<=0;request_bank<=0;request_enable<=0;image_enable<=0;shown_mode<=0;
   video_frames<=0;underflow<=0;last_underflow<=0;underflow_seen<=0;hs<=0;vs<=0;de<=0;red<=0;green<=0;blue<=0;
  end else begin
   if(x==2199) begin x<=0;if(y==1124)y<=0;else y<=y+1'b1;end else x<=x+1'b1;
   hs<=(x>=2008)&&(x<2052);vs<=(y>=1084)&&(y<1089);de<=(x<1920)&&(y<1080);
   {red,green,blue}<=color;
   if(image_enable&&inside_image&&!rf_valid)begin underflow<=underflow+1'b1;underflow_seen<=1;end
   if(x==0&&y==1080) begin
    video_frames<=video_frames+1'b1;last_underflow<=underflow;underflow<=0;
    shown_mode<=pubv2?2:0;request_bank<=pubb2;
    request_enable<=pubv2&&banks2[pubb2];
    image_enable<=pubv2&&banks2[pubb2];
    request_toggle<=!request_toggle;
   end
  end
 end
 (* async_reg="true" *) reg req1,req2,req3;
 reg req_seen,restart,read_enable,read_bank,read_active,ar_pending,last_burst,scan_started;
 reg [31:0] read_addr,line_base;reg [8:0] row;reg repeat_row;reg [3:0] col;
 reg [31:0] hash,frame_hash,read_frames;reg [3:0] beat;
 function [31:0] rol(input [31:0] d,input integer n);begin rol=(d<<n)|(d>>(32-n));end endfunction
 wire [31:0] hash_next=rol(hash,5)+(rdata[31:0]^rol(rdata[63:32],7)^rol(rdata[95:64],13)^rol(rdata[127:96],19));
 assign araddr=read_addr;assign arvalid=ar_pending;
 assign rready=read_active&&(restart||flush||rf_ready);
 wire rf_write=rvalid&&rready&&!restart&&!flush;
 // Drop DDR pixel padding, double the depth, and reserve one complete burst.
 wire [95:0] compact_read={rdata[119:96],rdata[87:64],rdata[55:32],rdata[23:0]};
 sc_async_fifo #(.W(96),.AW(9)) display_fifo(ac,arst||flush,compact_read,rf_write,rf_ready,
  pc,pf_reset,rf_data,rf_valid,rf_take,rf_level);
 always @(posedge ac) begin
  req1<=request_toggle;req2<=req1;req3<=req2;
  if(arst) begin
   req_seen<=0;restart<=0;read_bank<=0;scan_started<=0;read_enable<=0;read_active<=0;ar_pending<=0;flush_count<=63;
   read_frames<=0;frame_hash<=0;hash<=0;read_errors<=0;row<=0;col<=0;repeat_row<=0;line_base<=0;beat<=0;
  end else begin
   if(flush_count!=0)flush_count<=flush_count-1'b1;
   if(req3!=req_seen) begin req_seen<=req3;restart<=1;flush_count<=63;end
   if(ar_pending&&arready) begin ar_pending<=0;read_active<=1;beat<=0;end
   if(rvalid&&rready) begin
    if(rresp!=0||rlast!=(beat==15))read_errors<=read_errors+1'b1;
    beat<=beat+1'b1;
    if(!restart&&!flush)hash<=hash_next;
    if(rlast) begin
     read_active<=0;
     if(last_burst&&!restart&&!flush)begin frame_hash<=hash_next;read_frames<=read_frames+1'b1;read_enable<=0;end
    end
   end
   if(restart&&!read_active&&!ar_pending) begin
    restart<=0;flush_count<=63;read_enable<=request_enable&&calibrated;read_bank<=request_bank;if(request_enable&&calibrated)scan_started<=1;
    row<=0;col<=0;repeat_row<=0;line_base<=0;hash<=0;
   end else if(!restart&&!flush&&!read_active&&!ar_pending&&read_enable&&rf_level<=496) begin
    read_addr<=32'h400000+(read_bank?32'h200000:0)+line_base+{20'd0,col,8'd0};ar_pending<=1;
    last_burst<=(row==IH-1)&&(col==COLS-1)&&repeat_row;
    if(col==COLS-1) begin
     col<=0;repeat_row<=!repeat_row;
     if(repeat_row)begin row<=row+1'b1;line_base<=line_base+IW*4;end
    end else col<=col+1'b1;
   end
  end
 end
 assign shown_valid=published_valid&&scan_started;assign shown_bank=read_bank;
 // Diagnostic snapshots only: the host accepts the stable CRC after two complete scans.
 reg [127:0] d1,d2;reg [63:0] p1,p2;reg [1:0] vb1,vb2;reg uf1,uf2;
 always @(posedge uc)begin
  d1<={write_errors+read_errors,frame_hash,read_frames,write_words};d2<=d1;
  p1<={video_frames,last_underflow};p2<=p1;vb1<=valid_banks;vb2<=vb1;
  uf1<=underflow_seen;uf2<=uf1;
 end
 assign status={30'd0,mode,p2[63:32],p2[31:0],d2[127:96],d2[95:64],d2[63:32],d2[31:0],26'd0,uf2,cal2,vb2,mode};
endmodule
