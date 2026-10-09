// SC431HAI native orientation: BGGR RAW10, four samples per clock.
// Horizontal mirror is applied to RGB in sc_capture, after reconstruction.
// Reconstruct EVERY Bayer site with the reference 5x5 MHC coefficients.
// Apply the reference display Gamma to each reconstructed RGB pixel, then
// average 2x2 RGB pixels in the central 1280x960 crop to output 640x480.
// Per-channel Q8.8 gains precede interpolation, as in the camera example.
module sc_camera_rgb #(parameter IW=1920,IH=1080,OW=640,OH=480,
 parameter GAMMA_FILE="model/camera_gamma.mem")(
 input clk,rst,input vs,input valid,input [39:0] raw,
 output reg [47:0] rgb,output reg rgb_valid,sof,eof,
 output reg [31:0] frames,format_errors,
 input [15:0] rgb_r_gain,rgb_g_gain,rgb_b_gain,input rgb_request,output reg rgb_ack);
 localparam LEFT=(IW-OW*2)/2,TOP=(IH-OH*2)/2,WORDS=IW/4,AW=$clog2(OW/2);
 reg vs_d,armed,started;reg [11:0] x,y;reg [31:0] samples;
 wire edge_vs=vs!=vs_d;
 wire first=valid&&(armed||edge_vs);
 wire accept=valid&&(started||first);
 wire [11:0] xx=first?12'd0:x,yy=first?12'd0:y;
 function [7:0] black(input [9:0] v);
  begin black=(v[9:2] > 8'd16) ? (v[9:2]-8'd16) : 8'd0;end
 endfunction
 // Bundled gain data is held in the core clock domain until acknowledgement.
 // Synchronise the request for three clocks and data for two, then apply all
 // three channels only at the first RAW beat of a new sensor frame.
 (* async_reg="true" *) reg [2:0] gain_req_sync;
 reg [47:0] gain_data1, gain_data2;
 reg [15:0] active_r, active_g, active_b;
 wire gain_pending=gain_req_sync[2]!=rgb_ack;
 wire [47:0] frame_gains=(first&&gain_pending)?gain_data2:{active_r,active_g,active_b};
 wire [15:0] frame_r=frame_gains[47:32], frame_g=frame_gains[31:16], frame_b=frame_gains[15:0];
 always @(posedge clk) begin
  if(rst) begin
   gain_req_sync<=0; gain_data1<={16'd256,16'd256,16'd256};
   gain_data2<={16'd256,16'd256,16'd256};
   active_r<=256; active_g<=256; active_b<=256; rgb_ack<=0;
  end else begin
   gain_req_sync<={gain_req_sync[1:0],rgb_request};
   gain_data1<={rgb_r_gain,rgb_g_gain,rgb_b_gain}; gain_data2<=gain_data1;
   if(first&&gain_pending) begin
    {active_r,active_g,active_b}<=gain_data2;
    rgb_ack<=gain_req_sync[2];
   end
  end
 end
 // Exact reference gain math: 16-bit Q8.8, zero input falls back to 255/256.
 // Gains multiply black-corrected Bayer samples, before MHC
 // and Gamma. Native BGGR is B G on even rows and G R on odd rows.
 function [7:0] scaled(input [9:0] sample, input [15:0] gain);
  reg [23:0] product;
  begin
   product=black(sample)*(gain ? gain : 16'd255);
   scaled=(|product[23:16])?8'hff:product[15:8];
  end
 endfunction
 wire [15:0] gain_even=yy[0]?frame_g:frame_b;
 wire [15:0] gain_odd=yy[0]?frame_r:frame_g;
 wire [31:0] bytes_raw={scaled(raw[39:30],gain_odd),scaled(raw[29:20],gain_even),
                       scaled(raw[19:10],gain_odd),scaled(raw[9:0],gain_even)};

 // Four rotating RAW8 row banks. Delayed writes avoid address collisions.
 reg [31:0] line0[0:WORDS-1],line1[0:WORDS-1],line2[0:WORDS-1],line3[0:WORDS-1];
 reg [31:0] q0,q1,q2,q3,qraw;reg [11:0] qx,qy;reg qvalid;
 always @(posedge clk)begin
  if(accept&&!rst)begin
   q0<=line0[xx>>2];q1<=line1[xx>>2];q2<=line2[xx>>2];q3<=line3[xx>>2];
  end
  if(qvalid&&!rst)case(qy[1:0])
   0:line0[qx>>2]<=qraw;1:line1[qx>>2]<=qraw;
   2:line2[qx>>2]<=qraw;3:line3[qx>>2]<=qraw;
  endcase
 end
 reg [31:0] m2,m1,z0,p1;
 always @*case(qy[1:0])
  0:begin m2=q0;m1=q1;z0=q2;p1=q3;end
  1:begin m2=q1;m1=q2;z0=q3;p1=q0;end
  2:begin m2=q2;m1=q3;z0=q0;p1=q1;end
  3:begin m2=q3;m1=q0;z0=q1;p1=q2;end
 endcase
 reg [31:0] prev_m2,prev_m1,prev_z0,prev_p1,prev_p2;
 reg [15:0] left_m1,left_z0,left_p1;
 wire [95:0] zw={z0,prev_z0,left_z0,16'd0};
 wire [95:0] uw={m1,prev_m1,left_m1,16'd0};
 wire [95:0] dw={p1,prev_p1,left_p1,16'd0};
 wire window_valid=qvalid&&qy>=TOP+2&&qy<TOP+OH*2+2&&qx>=LEFT+4&&qx<LEFT+OW*2+4;
 reg v1,v2,v3,v4,v5,v6;
 reg y1,y2,y3,y4,y5;
 reg s1,s2,s3,s4,s5,s6,e1,e2,e3,e4,e5,e6;
 reg [AW-1:0] a1,a2,a3,a4,a5;
 // Implement the unchanged reference curve in logic: twelve parallel reads
 // otherwise duplicate twelve block RAMs in this nearly full SoC design.
 (* syn_romstyle="logic" *) reg [9:0] gamma[0:1023];
 initial $readmemh(GAMMA_FILE,gamma);

 function [7:0] clip(input signed [14:0] numerator);
  begin
   if(numerator<0)clip=0;
   else if(numerator>=4080)clip=255;
   else clip=numerator[11:4];
  end
 endfunction
 wire [7:0] enc_r[0:3],enc_g[0:3],enc_b[0:3];
 genvar pixel;
 generate for(pixel=0;pixel<4;pixel=pixel+1)begin:mhc
  localparam C=32+pixel*8;
  reg [7:0] center,center2;
  reg [8:0] far_h,far_v,near_h,near_v;
  reg [9:0] diag;
  wire signed [14:0] cs=$signed({7'd0,center});
  wire signed [14:0] hs=$signed({6'd0,far_h}),vs=$signed({6'd0,far_v});
  wire signed [14:0] ns=$signed({6'd0,near_h}),nv=$signed({6'd0,near_v});
  wire signed [14:0] ds=$signed({5'd0,diag});
  wire chroma= (pixel%2==0)?!y1:y1;
  reg signed [14:0] value_a,value_b;
  reg [7:0] linear_r,linear_g,linear_b;
  reg [7:0] display_r,display_g,display_b;
  wire [7:0] ca=clip(value_a),cb=clip(value_b);
  always @(posedge clk)begin
   if(window_valid)begin
    center<=prev_z0[pixel*8+:8];
    far_h<={1'b0,zw[C-16+:8]}+{1'b0,zw[C+16+:8]};
    far_v<={1'b0,prev_m2[pixel*8+:8]}+{1'b0,prev_p2[pixel*8+:8]};
    near_h<={1'b0,zw[C-8+:8]}+{1'b0,zw[C+8+:8]};
    near_v<={1'b0,prev_m1[pixel*8+:8]}+{1'b0,prev_p1[pixel*8+:8]};
    diag<={2'b0,uw[C-8+:8]}+{2'b0,uw[C+8+:8]}+{2'b0,dw[C-8+:8]}+{2'b0,dw[C+8+:8]};
   end
   if(v1)begin
    center2<=center;
    // Chroma sites: A=G, B=opposite chroma. Green sites: A=horizontal
    // chroma, B=vertical chroma. Coefficients exactly match raw_to_rgb.v.
    value_a<=(cs<<<3)+(chroma?15'sd0:(cs<<<1))-(hs<<<1)+
             (chroma?-(vs<<<1):vs)+(chroma?(ns<<<2):(ns<<<3))+
             (chroma?(nv<<<2):-(ds<<<1));
    value_b<=(cs<<<3)+(chroma?(cs<<<2):(cs<<<1))+
             (chroma?(-hs-(hs<<<1)):hs)-(vs<<<1)-(chroma?vs:15'sd0)+
             (chroma?(ds<<<2):((nv<<<3)-(ds<<<1)));
   end
   if(v2)begin
    if(pixel%2==0)begin
     if(y2)begin linear_r<=ca;linear_g<=center2;linear_b<=cb;end
     else begin linear_r<=cb;linear_g<=ca;linear_b<=center2;end
    end else begin
     if(y2)begin linear_r<=center2;linear_g<=ca;linear_b<=cb;end
     else begin linear_r<=cb;linear_g<=center2;linear_b<=ca;end
    end
   end
   if(v3)begin
    display_r<=gamma[{linear_r,linear_r[7:6]}]>>2;
    display_g<=gamma[{linear_g,linear_g[7:6]}]>>2;
    display_b<=gamma[{linear_b,linear_b[7:6]}]>>2;
   end
  end
  assign enc_r[pixel]=display_r;assign enc_g[pixel]=display_g;assign enc_b[pixel]=display_b;
 end endgenerate

 // Horizontal sums of two Gamma-encoded pixels need nine bits. Buffer the
 // even RGB row, then combine with the odd row for a rounded 2x2 box average.
 reg [53:0] row_rgb[0:OW/2-1];
 reg [53:0] horizontal,upper,lower;
 wire [9:0] avg_r0={1'b0,upper[8:0]}+{1'b0,lower[8:0]}+10'd2;
 wire [9:0] avg_g0={1'b0,upper[17:9]}+{1'b0,lower[17:9]}+10'd2;
 wire [9:0] avg_b0={1'b0,upper[26:18]}+{1'b0,lower[26:18]}+10'd2;
 wire [9:0] avg_r1={1'b0,upper[35:27]}+{1'b0,lower[35:27]}+10'd2;
 wire [9:0] avg_g1={1'b0,upper[44:36]}+{1'b0,lower[44:36]}+10'd2;
 wire [9:0] avg_b1={1'b0,upper[53:45]}+{1'b0,lower[53:45]}+10'd2;
 always @(posedge clk)begin
  if(v5&&!y5&&!rst)row_rgb[a5]<=horizontal;
  if(v5&&y5&&!rst)begin upper<=row_rgb[a5];lower<=horizontal;end
 end
 always @(posedge clk)begin
  if(rst)begin
   vs_d<=0;armed<=0;started<=0;x<=0;y<=0;samples<=0;frames<=0;format_errors<=0;qvalid<=0;qx<=0;qy<=0;
   prev_m2<=0;prev_m1<=0;prev_z0<=0;prev_p1<=0;prev_p2<=0;left_m1<=0;left_z0<=0;left_p1<=0;
   v1<=0;v2<=0;v3<=0;v4<=0;v5<=0;v6<=0;
   s1<=0;s2<=0;s3<=0;s4<=0;s5<=0;s6<=0;e1<=0;e2<=0;e3<=0;e4<=0;e5<=0;e6<=0;
   rgb_valid<=0;sof<=0;eof<=0;rgb<=0;
  end else begin
   vs_d<=vs;if(edge_vs&&!valid)armed<=1;qvalid<=accept;
   if(accept)begin
    qx<=xx;qy<=yy;qraw<=bytes_raw;
    if(first)begin
     if(started&&samples!=IW*IH)format_errors<=format_errors+1'b1;
     frames<=frames+1'b1;samples<=4;armed<=0;started<=1;
    end else samples<=samples+4;
    if(xx==IW-4)begin x<=0;y<=yy+1'b1;end else begin x<=xx+4;y<=yy;end
   end
   if(qvalid)begin
    prev_m2<=m2;prev_m1<=m1;prev_z0<=z0;prev_p1<=p1;prev_p2<=qraw;
    left_m1<=qx==0?16'd0:prev_m1[31:16];left_z0<=qx==0?16'd0:prev_z0[31:16];left_p1<=qx==0?16'd0:prev_p1[31:16];
   end
   v1<=window_valid;y1<=qy[0];a1<=(qx-LEFT-4)>>2;
   s1<=window_valid&&(qy==TOP+3)&&(qx==LEFT+4);
   e1<=window_valid&&(qy==TOP+OH*2+1)&&(qx==LEFT+OW*2);
   v2<=v1;y2<=y1;a2<=a1;s2<=s1;e2<=e1;
   v3<=v2;y3<=y2;a3<=a2;s3<=s2;e3<=e2;
   v4<=v3;y4<=y3;a4<=a3;s4<=s3;e4<=e3;
   v5<=v4;y5<=y4;a5<=a4;s5<=s4;e5<=e4;
   if(v4)begin
    horizontal[8:0]<={1'b0,enc_r[0]}+{1'b0,enc_r[1]};
    horizontal[17:9]<={1'b0,enc_g[0]}+{1'b0,enc_g[1]};
    horizontal[26:18]<={1'b0,enc_b[0]}+{1'b0,enc_b[1]};
    horizontal[35:27]<={1'b0,enc_r[2]}+{1'b0,enc_r[3]};
    horizontal[44:36]<={1'b0,enc_g[2]}+{1'b0,enc_g[3]};
    horizontal[53:45]<={1'b0,enc_b[2]}+{1'b0,enc_b[3]};
   end
   v6<=v5&&y5;s6<=s5;e6<=e5;
   rgb_valid<=v6;sof<=v6&&s6;eof<=v6&&e6;
   if(v6)rgb<={avg_b1[9:2],avg_g1[9:2],avg_r1[9:2],avg_b0[9:2],avg_g0[9:2],avg_r0[9:2]};
  end
 end
endmodule
