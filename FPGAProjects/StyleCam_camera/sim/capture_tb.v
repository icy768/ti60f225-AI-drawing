module tb;
 reg cc=0,ac=0;always #10 cc=~cc;always #5 ac=~ac;
 reg rst=1;reg [47:0] rgb=0;reg cv=0,sof=0,eof=0,take=0,release_f=0;
 wire ready,rb,locked,lb;wire [31:0] completed,skipped,errors,overflow;
 wire [31:0] ca,awaddr;wire cav,car,cwv,cwr,cbv,cbr;wire [127:0] cd;
 reg [31:0] na=32'h400000;reg nav=0,nwv=0,nbr=0;reg [127:0] nd=0;wire nar,nwr,nbv;
 wire av,wv,br;wire [127:0] wd;
 reg ar=0,wr=0,bv=0;reg [31:0] address;reg [1:0] bus=0;integer delay_b=0,cycle=0,net_words=0;
 reg [127:0] memory[0:23];integer camera_words=0;reg bad_response=0;reg [1:0] response=0;
 sc_capture #(.PIXELS(48),.FIFO_AW(6)) cap(cc,rst,rgb,cv,sof,eof,ac,rst,1'b1,take,release_f,ready,rb,locked,lb,completed,skipped,errors,overflow,ca,cav,car,cd,cwv,cwr,cbv,response,cbr);
 sc_write_arbiter arb(ac,rst,ca,cav,car,cd,cwv,cwr,cbv,cbr,na,nav,nar,nd,nwv,nwr,nbv,nbr,awaddr,av,ar,wd,wv,wr,bv,br);
 reg [1:0] net_state=0;
 always @(posedge ac)begin
  if(rst)begin bus<=0;ar<=0;wr<=0;bv<=0;net_state<=0;nav<=0;nwv<=0;nbr<=0;end
  else begin
   cycle<=cycle+1;ar<=(bus==0)&&(cycle%3!=0);wr<=(bus==1)&&(cycle%4!=0);
   if(av&&ar)begin
    if(bus!=0)$fatal(1,"AXI AW collision");address<=awaddr;bus<=1;ar<=0;
    if(awaddr<32'h400000&&locked&&awaddr[21]==lb)$fatal(1,"Overwrote locked input bank");
   end
   if(wv&&wr)begin
    if(bus!=1)$fatal(1,"AXI W without AW");bus<=2;wr<=0;delay_b<=cycle%7+1;response<=(bad_response&&address<32'h400000) ? 2 : 0;
    if(address<32'h400000)begin memory[address[21]*12+address[19:4]]<=wd;camera_words<=camera_words+1;end
    else begin if(wd!=={96'd0,32'habc00000+net_words})$fatal(1,"Output writer corruption");net_words<=net_words+1;end
   end
   if(bus==2&&!bv)begin if(delay_b==0)bv<=1;else delay_b<=delay_b-1;end
   if(bv&&br)begin bv<=0;bus<=0;end
   case(net_state)
    0:if(net_words<20)begin na<=32'h400000+net_words*16;nd<={96'd0,32'habc00000+net_words};nav<=1;net_state<=1;end
    1:if(nav&&nar)begin nav<=0;nwv<=1;net_state<=2;end
    2:if(nwv&&nwr)begin nwv<=0;nbr<=1;net_state<=3;end
    3:if(nbv&&nbr)begin nbr<=0;net_state<=0;end
   endcase
  end
 end
 task frame(input integer base,input integer omit);
  integer i;begin
   for(i=0;i<24;i=i+1)begin
    @(negedge cc);cv=(i!=omit);sof=(i==0);eof=(i==23);rgb={24'(base+i*2+1),24'(base+i*2)};
   end
   @(negedge cc);cv=0;sof=0;eof=0;repeat(1000)@(negedge ac);
  end
 endtask
 task lock_frame;begin wait(ready);@(negedge ac);take=1;@(negedge ac);take=0;wait(locked);end endtask
 task unlock;begin @(negedge ac);release_f=1;@(negedge ac);release_f=0;end endtask
 task check_bank(input integer bank,input integer base);
  integer i,k;begin
   for(i=0;i<12;i=i+1)for(k=0;k<4;k=k+1)
    if(memory[bank*12+i][k*32+:32]!==32'(base+i*4+k))$fatal(1,"Capture bank %0d word %0d lane %0d",bank,i,k);
  end
 endtask
 initial begin
  repeat(8)@(negedge ac);rst=0;
  frame(100,-1);if(completed!=1)$fatal(1,"First commit");check_bank(0,100);lock_frame;
  frame(200,-1);if(completed!=2)$fatal(1,"Second commit");check_bank(1,200);
  frame(300,-1);if(completed!=2||skipped!=1)$fatal(1,"Busy frame was not skipped");check_bank(0,100);check_bank(1,200);
  unlock;lock_frame;if(lb!=1)$fatal(1,"Second frame ownership");
  frame(400,10);if(completed!=2||errors!=1)$fatal(1,"Partial frame published");
  frame(500,-1);if(completed!=3)$fatal(1,"Recovery from partial frame");check_bank(0,500);
  unlock;lock_frame;if(lb!=0)$fatal(1,"Recovered bank ownership");
  bad_response=1;frame(600,-1);bad_response=0;if(completed!=3||errors<2)$fatal(1,"AXI error frame published");
  frame(700,-1);if(completed!=4)$fatal(1,"Recovery from AXI error");check_bank(1,700);
  if(overflow||net_words!=20)$fatal(1,"FIFO overflow or arbiter starvation");
  rst=1;repeat(5)@(negedge ac);if(ready||locked||completed||errors)$fatal(1,"Capture reset");
  $display("PASS capture/AXI: 4 complete frames, locked-bank protection, whole-frame skip, partial-frame rejection, AXI error rejection/recovery, concurrent output writer, reset");$finish;
 end
 initial begin #1000000;$fatal(1,"Capture timeout");end
endmodule
