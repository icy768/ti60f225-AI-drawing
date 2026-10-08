// SC431HAI horizontal mirror (3221=06): GBRG RAW10, four adjacent samples per clock.
// Crop the central 1280x960 region and average each 2x2 Bayer cell to RGB.
// No camera backpressure. Output contains two RGB888 pixels per valid beat.
module sc_camera_rgb #(parameter IW=1920,IH=1080,OW=640,OH=480,
 parameter GAMMA_FILE="model/camera_gamma.mem")(
 input clk,rst,input vs,input valid,input [39:0] raw,
 output reg [47:0] rgb,output reg rgb_valid,sof,eof,
 output reg [31:0] frames,format_errors);
 localparam LEFT=(IW-OW*2)/2,TOP=(IH-OH*2)/2;
 reg vs_d,armed,started;reg [11:0] x,y;reg [31:0] samples;
 wire edge_vs=vs!=vs_d;
 wire first=valid&&(armed||edge_vs);
 wire [11:0] xx=first?12'd0:x,yy=first?12'd0:y;
 wire cropped=valid&&(started||first)&&xx>=LEFT&&xx<LEFT+OW*2&&yy>=TOP&&yy<TOP+OH*2;
 wire [8:0] addr=(xx-LEFT)>>2;
 function [7:0] black(input [9:0] v);begin black=v[9:2]>16?v[9:2]-8'd16:0;end endfunction
 wire [31:0] bytes_raw={black(raw[39:30]),black(raw[29:20]),black(raw[19:10]),black(raw[9:0])};
 reg [31:0] line[0:OW/2-1];reg [31:0] prev,bottom;
 reg v1,s1,e1;
 reg [9:0] gamma[0:1023];initial $readmemh(GAMMA_FILE,gamma);
 wire [8:0] green0={1'b0,prev[7:0]}+{1'b0,bottom[15:8]}+1;
 wire [8:0] green1={1'b0,prev[23:16]}+{1'b0,bottom[31:24]}+1;
 wire [7:0] g0=green0[8:1],g1=green1[8:1];
 always @(posedge clk)begin
  if(rst)begin vs_d<=0;armed<=0;started<=0;x<=0;y<=0;samples<=0;frames<=0;format_errors<=0;v1<=0;s1<=0;e1<=0;rgb_valid<=0;sof<=0;eof<=0;rgb<=0;end
  else begin
   vs_d<=vs;v1<=0;s1<=0;e1<=0;
   if(edge_vs&&!valid)armed<=1;
   if(valid&&(started||first))begin
    if(first)begin
     if(started&&samples!=IW*IH)format_errors<=format_errors+1'b1;
     frames<=frames+1'b1;samples<=4;armed<=0;started<=1;
    end else samples<=samples+4;
    if(xx==IW-4)begin x<=0;y<=yy+1'b1;end else begin x<=xx+4;y<=yy;end
   end
   if(cropped)begin
    if(!yy[0])line[addr]<=bytes_raw;
    else begin
     prev<=line[addr];bottom<=bytes_raw;v1<=1;
     s1<=(yy==TOP+1)&&(xx==LEFT);
     e1<=(yy==TOP+OH*2-1)&&(xx==LEFT+OW*2-4);
    end
   end
   rgb_valid<=v1;sof<=s1;eof<=e1;
   if(v1)begin
    rgb[7:0]<=gamma[{bottom[7:0],bottom[7:6]}]>>2;
    rgb[15:8]<=gamma[{g0,g0[7:6]}]>>2;
    rgb[23:16]<=gamma[{prev[15:8],prev[15:14]}]>>2;
    rgb[31:24]<=gamma[{bottom[23:16],bottom[23:22]}]>>2;
    rgb[39:32]<=gamma[{g1,g1[7:6]}]>>2;
    rgb[47:40]<=gamma[{prev[31:24],prev[31:30]}]>>2;
   end
  end
 end
endmodule
