// Two 640x480 RGB output stores in DDR; HDMI 1080p60 with three layouts and an OSD layer.
// mode 0: original (left) | stylized (right), each 1.5x nearest (960x720), y 180..899.
//   Output lines repeat source rows as 0,0,1,2,2,3..: the first copy is kept in a one-row cache, so
//   DDR reads each source row once (same burst count per frame as the 2x layouts).
// mode 1: stylized 2x (1280x960 centred);  mode 2: original 2x
// The original shown beside a stylized frame is the exact input frame that produced it
// (publish_orig names its input bank, which sc_capture holds until the next frame is shown).
// OSD: 80x23 character grid, 8x16 font scaled 3x (24x48 px); code 0 transparent, bit7 = highlight.
module sc_display #(parameter IW=640,IH=480,FONT="model/font8x16.mem",TEXT="model/osd_text.mem")(
 input uc,input urst,input ac,input arst,input pc,input prst,input calibrated,
 input [23:0] pixel,input pv,output pready,input new_frame,input original_frame,
 input [1:0] mode,output [255:0] status,
 input write_bank,publish,publish_bank,input [1:0] publish_orig,
 output output_complete,output shown_valid,shown_bank,
 input osd_we,input [10:0] osd_addr,input [7:0] osd_data,
 output [31:0] awaddr,output awvalid,input awready,
 output [127:0] wdata,output wvalid,input wready,input bvalid,input [1:0] bresp,output bready,
 output [31:0] araddr,output arvalid,input arready,
 input [127:0] rdata,input rvalid,input rlast,input [1:0] rresp,output rready,
 output reg hs,vs,de,output reg [7:0] red,green,blue);
 localparam WORDS=IW*IH/4,COLS=IW/64;
 // layout (1080p active 1920x1080)
 localparam FX0=960-IW,FY0=540-IH;                    // 2x full screen
 localparam SW=IW*3/2,SH=IH*3/2,SX0=960-SW,SY0=540-SH/2; // 1.5x side by side
 function [31:0] in_base(input [1:0] b);begin in_base=(b==0)?32'h0:(b==1)?32'h200000:32'h800000;end endfunction
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
 reg published_valid,published_bank;reg [1:0] published_orig;
 always @(posedge ac)begin
  if(arst)begin published_valid<=0;published_bank<=0;published_orig<=0;end
  else if(publish)begin published_valid<=1;published_bank<=publish_bank;published_orig<=publish_orig;end
 end
 (* async_reg="true" *) reg pubv1,pubv2,pubb1,pubb2;
 (* async_reg="true" *) reg [1:0] pubo1,pubo2;
 always @(posedge pc)begin
  if(prst)begin pubv1<=0;pubv2<=0;pubb1<=0;pubb2<=0;pubo1<=0;pubo2<=0;end
  else begin pubv1<=published_valid;pubv2<=pubv1;pubb1<=published_bank;pubb2<=pubb1;pubo1<=published_orig;pubo2<=pubo1;end
 end
 // Request a fresh DDR scan during vertical blank; this also recovers alignment after underflow.
 reg [11:0] x,y;reg request_toggle,request_bank,request_enable;reg [1:0] request_orig,request_mode;
 reg image_enable;reg [1:0] shown_mode,dm;
 (* async_reg="true" *) reg [1:0] mode1,mode2,banks1,banks2;
 reg [31:0] video_frames,underflow,last_underflow;reg underflow_seen;
 wire inside_full=(x>=FX0)&&(x<FX0+IW*2)&&(y>=FY0)&&(y<FY0+IH*2);
 wire inside_sbs=(x>=SX0)&&(x<960+SW)&&(y>=SY0)&&(y<SY0+SH);
 wire inside_image=(dm==0)?inside_sbs:inside_full;
 wire rf_valid,rf_take,rf_ready;wire [95:0] rf_data;
 wire [9:0] rf_level;
 reg [5:0] flush_count;wire flush=(flush_count!=0);
 (* async_reg="true" *) reg flush1,flush2;
 wire pf_reset=prst||flush2;
 // 1.5x: six output pixels per FIFO word of four, source pixel pattern 0,0,1,2,2,3
 reg [2:0] c6;
 wire [1:0] sbs_index=c6==0?0:c6==1?0:c6==2?1:c6==3?2:c6==4?2:3;
 wire [1:0] pick=(dm==0)?sbs_index:x[2:1];
 wire last_of_word=(dm==0)?(c6==5):(x[2:0]==7);
 // side-by-side row cache: line phase 0 stores the row, phase 1 replays it, phase 2 shows the next row
 reg [1:0] pph;reg [8:0] wi;
 wire use_cache=(dm==0)&&(pph==1);
 wire [95:0] cache_q;
 wire [8:0] cache_ra=(x==2199)?9'd0:(inside_image&&last_of_word)?wi+1'b1:wi;
 sdpram #(.W(96),.D(IW/2),.AW(9)) row_cache(.clk(pc),.we((dm==0)&&(pph==0)&&image_enable&&inside_image&&last_of_word&&rf_valid),
  .waddr(wi),.wdata(rf_data),.re(1'b1),.raddr(cache_ra),.rdata(cache_q));
 assign rf_take=image_enable&&inside_image&&last_of_word&&!pf_reset&&!use_cache;
 wire [95:0] src_word=use_cache?cache_q:rf_data;
 wire src_valid=use_cache||rf_valid;
 wire [23:0] selected_pixel=src_word>>(pick*24);
 reg [23:0] color;
 always @* begin
  if(x<240)color=24'hffffff;else if(x<480)color=24'hffff00;
  else if(x<720)color=24'h00ffff;else if(x<960)color=24'h00ff00;
  else if(x<1200)color=24'hff00ff;else if(x<1440)color=24'hff0000;
  else if(x<1680)color=24'h0000ff;else color=24'h202020;
  if(image_enable) begin
   color=24'h101010;
   if(dm!=0&&(x>=FX0-4)&&(x<FX0+IW*2+4)&&(y>=FY0-4)&&(y<FY0+IH*2+4)) color=(shown_mode==1)?24'h20c060:24'h4080ff;
   if(inside_image)color=src_valid?{selected_pixel[7:0],selected_pixel[15:8],selected_pixel[23:16]}:24'hff00ff;
  end
 end
 // OSD character grid counters (24x48 cells)
 reg [6:0] cx;reg [4:0] sx,cy;reg [5:0] sy;
 wire [10:0] text_addr={cy,6'd0}+{cy,4'd0}+cx;
 wire [7:0] text_code;
 sc_dcram #(.W(8),.D(2048),.AW(11),.INIT(TEXT)) osd_text(uc,osd_we,osd_addr,osd_data,pc,text_addr,text_code);
 // stage registers: 1 text read, 2 font address/read, 3 compose
 reg [23:0] p1,p2,p3;reg a1,a2,a3,h1,h2,h3,v1,v2,v3;reg [3:0] fr1;reg [2:0] fb1,fb2,fb3;
 reg [7:0] code2,code3;reg [10:0] font_addr;wire [7:0] font_byte;
 wire [6:0] glyph=(text_code[6:0]>=32)?text_code[6:0]-7'd32:7'd0;
 sdpram #(.W(8),.D(1536),.AW(11),.INIT(FONT)) osd_font(.clk(pc),.we(1'b0),.waddr(11'd0),.wdata(8'd0),
  .re(1'b1),.raddr(font_addr),.rdata(font_byte));
 wire font_bit=font_byte[3'd7-fb3];
 wire [23:0] dim={1'b0,p3[23:17],1'b0,p3[15:9],1'b0,p3[7:1]};
 wire [23:0] ink=code3[7]?24'hffd040:24'hffffff;
 wire [23:0] osd_px=(code3==0)?p3:(font_bit?ink:dim);
 always @(posedge pc) begin
  mode1<=mode;mode2<=mode1;banks1<=valid_banks;banks2<=banks1;flush1<=flush;flush2<=flush1;
  if(prst) begin
   x<=0;y<=0;request_toggle<=0;request_bank<=0;request_enable<=0;request_orig<=0;request_mode<=0;image_enable<=0;shown_mode<=0;dm<=0;
   video_frames<=0;underflow<=0;last_underflow<=0;underflow_seen<=0;hs<=0;vs<=0;de<=0;red<=0;green<=0;blue<=0;
   c6<=0;cx<=0;sx<=0;cy<=0;sy<=0;pph<=0;wi<=0;
  end else begin
   if(x==2199) begin x<=0;if(y==1124)y<=0;else y<=y+1'b1;end else x<=x+1'b1;
   c6<=(x==SX0-1||x==2199)?3'd0:(c6==5)?3'd0:c6+1'b1;
   if(x==2199)begin wi<=0;if(y==SY0-1)pph<=0;else pph<=(pph==2)?2'd0:pph+1'b1;end
   else if(inside_image&&last_of_word)wi<=wi+1'b1;
   if(x==2199)begin cx<=0;sx<=0;
    if(y==1124)begin cy<=0;sy<=0;end else if(sy==47)begin sy<=0;cy<=cy+1'b1;end else sy<=sy+1'b1;
   end else if(sx==23)begin sx<=0;cx<=cx+1'b1;end else sx<=sx+1'b1;
   if(image_enable&&inside_image&&!src_valid)begin underflow<=underflow+1'b1;underflow_seen<=1;end
   if(x==0&&y==1080) begin
    video_frames<=video_frames+1'b1;last_underflow<=underflow;underflow<=0;
    shown_mode<=pubv2?2:0;request_bank<=pubb2;request_orig<=pubo2;request_mode<=mode2;dm<=mode2;
    request_enable<=pubv2&&banks2[pubb2];
    image_enable<=pubv2&&banks2[pubb2];
    request_toggle<=!request_toggle;
   end
   // OSD pipeline (video timing delayed to match)
   p1<=color;a1<=(x<1920)&&(y<1080);h1<=(x>=2008)&&(x<2052);v1<=(y>=1084)&&(y<1089);
   fr1<=sy/3;fb1<=sx/3;
   p2<=p1;a2<=a1;h2<=h1;v2<=v1;fb2<=fb1;code2<=text_code;font_addr<={glyph,4'd0}+fr1;
   p3<=p2;a3<=a2;h3<=h2;v3<=v2;fb3<=fb2;code3<=code2;
   hs<=h3;vs<=v3;de<=a3;{red,green,blue}<=a3?osd_px:24'h0;
  end
 end
 (* async_reg="true" *) reg req1,req2,req3;
 reg req_seen,restart,read_enable,read_bank,read_active,ar_pending,last_burst,scan_started;
 reg [1:0] read_orig,read_mode,ph;reg half;
 reg [31:0] read_addr,line_base;reg [8:0] row;reg [3:0] col;
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
 // Row order: mode 0 reads each source row once (original row then stylized row; the pixel side caches
 // it for the repeated output line); modes 1/2 read one row per output line, each row twice.
 wire sbs=read_mode==0;
 wire use_orig=(read_mode==2)||(sbs&&!half);
 wire [31:0] bank_base=use_orig?in_base(read_orig):(32'h400000+(read_bank?32'h200000:0));
 wire line_end=(col==COLS-1)&&(!sbs||half);
 wire row_step=sbs||(ph==1);
 always @(posedge ac) begin
  req1<=request_toggle;req2<=req1;req3<=req2;
  if(arst) begin
   req_seen<=0;restart<=0;read_bank<=0;read_orig<=0;read_mode<=0;scan_started<=0;read_enable<=0;read_active<=0;ar_pending<=0;flush_count<=63;
   read_frames<=0;frame_hash<=0;hash<=0;read_errors<=0;row<=0;col<=0;ph<=0;half<=0;line_base<=0;beat<=0;
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
    restart<=0;flush_count<=63;read_enable<=request_enable&&calibrated;read_bank<=request_bank;read_orig<=request_orig;read_mode<=request_mode;
    if(request_enable&&calibrated)scan_started<=1;
    row<=0;col<=0;ph<=0;half<=0;line_base<=0;hash<=0;
   end else if(!restart&&!flush&&!read_active&&!ar_pending&&read_enable&&rf_level<=496) begin
    read_addr<=bank_base+line_base+{20'd0,col,8'd0};ar_pending<=1;
    last_burst<=(row==IH-1)&&line_end&&(sbs||ph==1);
    if(col==COLS-1) begin
     col<=0;
     if(sbs&&!half)half<=1;
     else begin
      half<=0;ph<=sbs?2'd0:(ph==1)?2'd0:2'd1;
      if(row_step)begin row<=row+1'b1;line_base<=line_base+IW*4;end
     end
    end else col<=col+1'b1;
   end
  end
 end
 assign shown_valid=published_valid&&scan_started;assign shown_bank=read_bank;
 // Diagnostic snapshots only: the host accepts the stable CRC after two complete scans.
 reg [127:0] d1,d2;reg [63:0] p1s,p2s;reg [1:0] vb1,vb2;reg uf1,uf2;
 always @(posedge uc)begin
  d1<={write_errors+read_errors,frame_hash,read_frames,write_words};d2<=d1;
  p1s<={video_frames,last_underflow};p2s<=p1s;vb1<=valid_banks;vb2<=vb1;
  uf1<=underflow_seen;uf2<=uf1;
 end
 assign status={30'd0,mode,p2s[63:32],p2s[31:0],d2[127:96],d2[95:64],d2[63:32],d2[31:0],26'd0,uf2,cal2,vb2,mode};
endmodule
// Dual-clock simple dual-port RAM with optional init file (OSD text).
module sc_dcram #(parameter W=8,D=2048,AW=11,INIT="")(
 input wc,input we,input [AW-1:0] wa,input [W-1:0] wd,input rc,input [AW-1:0] ra,output reg [W-1:0] rd);
 reg [W-1:0] mem[0:D-1];
 integer k;
 initial begin for(k=0;k<D;k=k+1)mem[k]=0;if(INIT!="")$readmemh(INIT,mem);end
 always @(posedge wc) if(we) mem[wa]<=wd;
 always @(posedge rc) rd<=mem[ra];
endmodule
