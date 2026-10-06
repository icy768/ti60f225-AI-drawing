module tb;
 reg clk=0;always #5 clk=~clk;reg rst=1,key=1;
 reg ready=1,idle=1,done=0,ok=1,complete=0,shown_valid=0,shown_bank=0;reg [1:0] rb=0;reg [2:0] styles=0;
 wire take,release_f,hold_swap,start,mode,ob,pub,pb;wire [1:0] ib;wire [1:0] style,requested;wire [31:0] processed,errors,status;
 sc_video_schedule #(.KEY_CYCLES(3)) dut(clk,rst,key,ready,rb,take,release_f,ib,hold_swap,idle,done,ok,styles,start,style,mode,complete,shown_valid,shown_bank,ob,pub,pb,requested,processed,errors,status);
 integer started=0,committed=0,swaps=0;reg [1:0] held_input;reg held_output;integer delay_engine=0,delay_output=0,delay_display=0;
 always @(posedge clk)begin
  done<=0;
  if(!rst)begin
   if(take)begin ready<=0;held_input<=rb;rb<=rb==2?2'd0:rb+1'b1;end
   if(hold_swap)begin if(!(shown_valid&&shown_bank==pb))$fatal(1,"hold_swap before HDMI shows the bank");swaps<=swaps+1;end
   if(start)begin
    if(style!==2'(started%3)||mode!==(started>=3))$fatal(1,"Style/calibration mode start %0d",started);
    if(shown_valid&&ob==shown_bank)$fatal(1,"Writing HDMI front bank");
    held_output<=ob;idle<=0;complete<=0;started<=started+1;delay_engine<=32;
   end
   if(!idle)begin
    if(ib!==held_input||ob!==held_output)$fatal(1,"Frame ownership changed during inference");
    if(delay_engine==0)begin idle<=1;done<=1;styles[style]<=1;delay_output<=5;end else delay_engine<=delay_engine-1;
   end
   if(idle&&delay_output!=0)begin delay_output<=delay_output-1;if(delay_output==1)complete<=1;end
   if(pub)begin if(!complete)$fatal(1,"Published before final DDR completion");committed<=committed+1;delay_display<=10;end
   if(delay_display!=0)begin delay_display<=delay_display-1;if(delay_display==1)begin shown_valid<=1;shown_bank<=pb;end end
   if(release_f)ready<=1;
  end
 end
 task press;begin @(negedge clk);key=0;repeat(10)@(negedge clk);key=1;repeat(10)@(negedge clk);end endtask
 initial begin
  repeat(5)@(negedge clk);rst=0;
  wait(started==1);press;wait(started==2);press;wait(started==3);press;wait(started==4);
  ready=0;wait(processed==4);repeat(15)@(negedge clk);
  if(committed!=4||swaps!=4||requested!=0||styles!=7||errors)$fatal(1,"Scheduler totals");
  rst=1;repeat(5)@(negedge clk);if(processed||errors||requested)$fatal(1,"Schedule reset");
  $display("PASS schedule: frame lock, deferred style changes, initial IN per style, rotating refresh, final-write gate, HDMI bank acknowledgement, reset");$finish;
 end
 initial begin #100000;$fatal(1,"Schedule timeout");end
endmodule
