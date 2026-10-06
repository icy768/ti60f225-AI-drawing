`timescale 1ns/1ps
module thumbnail_tb;
 parameter ROI_MODE=0;
 parameter X0=32,Y0=8;
 reg pc=0,rc=0,reset=1,vs=0,valid=0;
 always #5 pc=~pc;
 always #7 rc=~rc;
 reg [31:0] pixels=0;
 wire active,want,tx;
 raw_thumbnail #(.WIDTH(80),.HEIGHT(20),.STRIDE(5),.OUT_W(16),.OUT_H(4),.UART_CYCLES(4),.ROI_MODE(ROI_MODE),.X0(X0),.Y0(Y0)) dut(
  .pixel_clk(pc),.ref_clk(rc),.reset(reset),.request(1'b1),.vs(vs),.valid(valid),
  .permit(1'b1),.raw_pixels(pixels),.active(active),.want(want),.tx(tx));
 reg [7:0] chars[0:191],ch;
 integer n=0,k,x,y,b,col,row;
 always @(negedge tx) if(!reset) begin
   #84;
   for(k=0;k<8;k=k+1) begin ch[k]=tx;#56;end
   if(tx!==1) $fatal(1,"Stop bit");
   chars[n]=ch;n=n+1;
 end
 function [7:0] code;
 input integer i,j;
 begin code=(i+7*j)%256;end
 endfunction
 task frame;
 input integer rows;
 begin
   @(negedge pc);vs=1;@(negedge pc);
   for(y=0;y<rows;y=y+1) begin
     for(x=0;x<80;x=x+4) begin
       pixels={code(x+3,y),code(x+2,y),code(x+1,y),code(x,y)};
       valid=1;@(negedge pc);valid=0;repeat(2) @(negedge pc);
     end
   end
   vs=0;valid=0;repeat(10) @(negedge pc);
 end
 endtask
 function integer hexval;
 input [7:0] c;
 begin
   if(c>="0" && c<="9") hexval=c-"0";
   else if(c>="A" && c<="F") hexval=c-"A"+10;
   else $fatal(1,"Non-hex payload");
 end
 endfunction
 integer i,pos,value;
 initial begin
   #80;@(negedge pc);reset=0;repeat(10) @(negedge pc);
   frame(5);if(want || active) $fatal(1,"Accepted incomplete frame");
   frame(20);wait(active);wait(!active);#100;
   if(n!=192) $fatal(1,"Missing UART data: %0d",n);
   for(b=0;b<2;b=b+1) begin
     if({chars[b*96],chars[b*96+1],chars[b*96+2],chars[b*96+3]}!==(ROI_MODE?"ROI1":"RAW1")) $fatal(1,"Tag");
     for(i=0;i<32;i=i+1) begin
       pos=b*96+23+(i/4)*9+(i%4)*2;
       value=hexval(chars[pos])*16+hexval(chars[pos+1]);
       row=(b*32+i)/16;col=(b*32+i)%16;
       if(value!==code(ROI_MODE?X0+col:col*5,ROI_MODE?Y0+row:row*5))
         $fatal(1,"Sample/order mismatch %0d: %0d",b*32+i,value);
     end
   end
   frame(20);repeat(100) @(negedge pc);
   if(n!=192) $fatal(1,"Snapshot was overwritten/repeated");
   $display("PASS RAW sampling ROI_MODE=%0d, all adjacent lanes/order, invalid gaps, short-frame retry, frozen buffer",ROI_MODE);$finish;
 end
 initial begin #1000000;$fatal(1,"Timeout");end
endmodule
