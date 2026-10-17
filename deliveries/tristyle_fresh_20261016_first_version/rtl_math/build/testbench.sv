`timescale 1ns/1ps
module testbench;
 localparam NCASES=728,NSAMPLES=47872,NMERGE=360,NROUND=156;
 reg clk=0;always #5 clk=~clk;
 reg rst=1,clear=0,valid=0;reg[7:0]x=0,zin=0;reg signed[7:0]w=0;
 reg signed[31:0]bias=0,mult=0;reg signed[7:0]expn=0;reg[7:0]zout=0;reg relu=0;
 wire signed[31:0]acc;wire overflow;wire[7:0]y;
 mac_dot8 mac(clk,rst,clear,valid,x,zin,w,bias,acc,overflow);
 requant32 rq(acc,mult,expn,zout,relu,y);
 reg[255:0]p[0:NCASES-1];reg[7:0]xs[0:NSAMPLES-1],ws[0:NSAMPLES-1];reg[255:0]mp[0:NMERGE-1];
 reg[7:0]a=0,b=0,za=0,zb=0,zo=0;reg signed[31:0]ma=0,mb=0;reg signed[7:0]ea=0,eb=0;reg use_b=0;wire[7:0]my;
 merge_requant8 mq(a,b,za,zb,zo,ma,mb,ea,eb,use_b,my);
 reg[191:0]rp[0:NROUND-1];reg signed[63:0]rx=0;reg signed[8:0]rsh=0;wire signed[63:0]ry;
 rne_shift64 rounder(rx,rsh,ry);
 integer i,j,off,n;
 initial begin
  $readmemh("params.mem",p);$readmemh("xs.mem",xs);$readmemh("ws.mem",ws);$readmemh("merge.mem",mp);$readmemh("round.mem",rp);
  repeat(2) @(negedge clk);rst=0;
  for(i=0;i<NCASES;i=i+1)begin
   @(negedge clk);clear=1;valid=0;bias=p[i][31:0];mult=p[i][63:32];expn=p[i][71:64];zin=p[i][79:72];zout=p[i][87:80];relu=p[i][88];off=p[i][160:129];n=p[i][176:161];
   @(negedge clk);clear=0;valid=1;x=xs[off];w=ws[off];
   for(j=1;j<n;j=j+1)begin @(negedge clk);x=xs[off+j];w=ws[off+j];end
   @(negedge clk);valid=0;#1;
   if(overflow || acc!==p[i][120:89] || y!==p[i][128:121])$fatal(1,"MAC_REQUANT case%0d acc%0d expected%0d y%0d expected%0d overflow%0d",i,acc,$signed(p[i][120:89]),y,p[i][128:121],overflow);
  end
  for(i=0;i<NMERGE;i=i+1)begin
   a=mp[i][7:0];b=mp[i][15:8];za=mp[i][23:16];zb=mp[i][31:24];zo=mp[i][39:32];ma=mp[i][71:40];mb=mp[i][103:72];ea=mp[i][111:104];eb=mp[i][119:112];use_b=mp[i][120];#2;
   if(my!==mp[i][128:121])$fatal(1,"MERGE case%0d y%0d expected%0d",i,my,mp[i][128:121]);
  end
  for(i=0;i<NROUND;i=i+1)begin rx=rp[i][63:0];rsh=rp[i][72:64];#2;if(ry!==rp[i][136:73])$fatal(1,"ROUND case%0d got%0d expected%0d",i,ry,$signed(rp[i][136:73]));end
  $display("PASS MAC_REQUANT=%0d MERGE=%0d ROUND=%0d SAMPLES=%0d",NCASES,NMERGE,NROUND,NSAMPLES);$finish;
 end
endmodule
