module tb;
 parameter MIRROR=0;
 reg cc=0,ac=0;always #10 cc=~cc;always #5 ac=~ac;
 reg rst=1;reg [47:0] rgb=0;reg cv=0,sof=0,eof=0,take=0,release_f=0,hold_pub=0,hold_swap=0;
 wire ready,locked;wire [1:0] rb,lb;wire [31:0] completed,skipped,errors,overflow;
 wire [31:0] ca,awaddr;wire cav,car,cwv,cwr,cbv,cbr;wire [127:0] cd;
 reg [31:0] na=32'h400000;reg nav=0,nwv=0,nbr=0;reg [127:0] nd=0;wire nar,nwr,nbv;
 wire av,wv,br;wire [127:0] wd;
 reg ar=0,wr=0,bv=0;reg [31:0] address;reg [1:0] bus=0;integer delay_b=0,cycle=0,net_words=0;
 reg [127:0] memory[0:35];integer camera_words=0;reg bad_response=0;reg [1:0] response=0;
 sc_capture #(.PIXELS(48),.FIFO_AW(6),.WIDTH(12),.H_MIRROR(MIRROR)) cap(cc,rst,rgb,cv,sof,eof,ac,rst,1'b1,take,release_f,hold_pub,hold_swap,ready,rb,locked,lb,completed,skipped,errors,overflow,ca,cav,car,cd,cwv,cwr,cbv,response,cbr);
 sc_write_arbiter arb(ac,rst,ca,cav,car,cd,cwv,cwr,cbv,cbr,na,nav,nar,nd,nwv,nwr,nbv,nbr,awaddr,av,ar,wd,wv,wr,bv,br);
 function [1:0] bank_of(input [31:0] a);begin bank_of=(a>=32'h800000)?2'd2:{1'b0,a[21]};end endfunction
 function camera_addr(input [31:0] a);begin camera_addr=(a<32'h400000)||(a>=32'h800000);end endfunction
 reg [1:0] net_state=0;
 always @(posedge ac)begin
  if(rst)begin bus<=0;ar<=0;wr<=0;bv<=0;net_state<=0;nav<=0;nwv<=0;nbr<=0;end
  else begin
   cycle<=cycle+1;ar<=(bus==0)&&(cycle%3!=0);wr<=(bus==1)&&(cycle%4!=0);
   if(av&&ar)begin
    if(bus!=0)$fatal(1,"AXI AW collision");address<=awaddr;bus<=1;ar<=0;
    if(camera_addr(awaddr))begin
     if(locked&&bank_of(awaddr)==lb)$fatal(1,"Overwrote locked input bank");
     if(cap.pend_valid&&bank_of(awaddr)==cap.pend_bank)$fatal(1,"Overwrote published original");
     if(cap.disp_valid&&bank_of(awaddr)==cap.disp_bank)$fatal(1,"Overwrote displayed original");
    end
   end
   if(wv&&wr)begin
    if(bus!=1)$fatal(1,"AXI W without AW");bus<=2;wr<=0;delay_b<=cycle%7+1;response<=(bad_response&&camera_addr(address)) ? 2 : 0;
    if(camera_addr(address))begin memory[bank_of(address)*12+address[19:4]]<=wd;camera_words<=camera_words+1;end
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
 task unlock(input bit hold);begin @(negedge ac);release_f=1;hold_pub=hold;@(negedge ac);release_f=0;hold_pub=0;end endtask
 task swap;begin @(negedge ac);hold_swap=1;@(negedge ac);hold_swap=0;end endtask
 task check_bank(input integer bank,input integer base);
  integer i,k;begin
   for(i=0;i<12;i=i+1)for(k=0;k<4;k=k+1)
    if(memory[bank*12+i][k*32+:32]!==32'(base+(MIRROR?((i*4+k)/12*12+11-(i*4+k)%12):i*4+k)))$fatal(1,"Capture bank %0d word %0d lane %0d",bank,i,k);
  end
 endtask
 initial begin
  repeat(8)@(negedge ac);rst=0;
  frame(100,-1);if(completed!=1||rb!=0)$fatal(1,"First commit");check_bank(0,100);lock_frame;if(lb!=0)$fatal(1,"Lock bank 0");
  frame(200,-1);if(completed!=2||rb!=1)$fatal(1,"Second commit");check_bank(1,200);
  frame(300,-1);if(completed!=3||skipped!=0||rb!=2||cap.ready_mask!=3'b100)$fatal(1,"Newest frame must replace the older READY frame");check_bank(2,300);
  unlock(1);if(cap.pend_valid!==1||cap.pend_bank!=0)$fatal(1,"Published input not held");
  lock_frame;if(lb!=2)$fatal(1,"Newest frame ownership");
  frame(400,-1);if(completed!=4||rb!=1)$fatal(1,"Free bank beside held/locked banks");check_bank(1,400);check_bank(0,100);
  frame(500,-1);if(completed!=4||skipped!=1)$fatal(1,"No free bank: frame must be skipped");check_bank(0,100);check_bank(1,400);check_bank(2,300);
  swap;if(!cap.disp_valid||cap.disp_bank!=0||cap.pend_valid)$fatal(1,"Swap to displayed");
  frame(600,-1);if(skipped!=2)$fatal(1,"Displayed bank must stay protected");check_bank(0,100);
  unlock(0);if(cap.pend_valid)$fatal(1,"Error release must not hold");
  frame(700,10);if(completed!=4||errors!=1)$fatal(1,"Partial frame published");
  frame(800,-1);if(completed!=5||rb!=2||cap.ready_mask!=3'b100)$fatal(1,"Recovery into freed bank");check_bank(2,800);check_bank(0,100);
  lock_frame;if(lb!=2)$fatal(1,"Lock recovered bank");unlock(1);swap;if(cap.disp_bank!=2)$fatal(1,"Second displayed bank");
  bad_response=1;frame(900,-1);bad_response=0;if(completed!=5||errors<2)$fatal(1,"AXI error frame published");
  frame(1000,-1);if(completed!=6)$fatal(1,"Recovery from AXI error");check_bank(2,800);
  if(overflow||net_words!=20)$fatal(1,"FIFO overflow or arbiter starvation");
  rst=1;repeat(5)@(negedge ac);if(ready||locked||completed||errors||cap.pend_valid||cap.disp_valid)$fatal(1,"Capture reset");
  $display("PASS capture/AXI: 3 banks, newest-only READY, locked/published/displayed original protection, whole-frame skip, partial-frame and AXI error rejection, concurrent output writer, reset");$finish;
 end
 initial begin #2000000;$fatal(1,"Capture timeout");end
endmodule
