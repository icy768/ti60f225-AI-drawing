`timescale 1ns/1ps
module tb #(parameter TICK=4,TIMEOUT=7);
 reg clk=0;always #5 clk=~clk;
 reg rst=1,start=0,read_op=0,scl=0,sda=0;
 reg [15:0] addr=0;reg [7:0] wd=0;
 wire sl,dl,busy,done,rsl,rdl,rb,rdone;
 wire [2:0] result,ref_result;wire [7:0] data,ref_data;
 integer cycles=0,before_cycle,i,seed=9876;
 i2c_reg16 #(.TICK_CYCLES(TICK),.TIMEOUT_TICKS(TIMEOUT)) dut(clk,rst,scl,sda,start,read_op,addr,wd,sl,dl,busy,done,result,data);
 i2c_reg16_resource1 #(.TICK_CYCLES(TICK),.TIMEOUT_TICKS(TIMEOUT)) reference(clk,rst,scl,sda,start,read_op,addr,wd,rsl,rdl,rb,rdone,ref_result,ref_data);
 always @(posedge clk)begin
  cycles=cycles+1;#1;
  if(!rst && {sl,dl,busy,done,result,data} !== {rsl,rdl,rb,rdone,ref_result,ref_data})
   $fatal(1,"I2C cycle equivalence failed");
 end
 initial begin
  repeat(5)@(negedge clk);rst=0;before_cycle=cycles;
  start=1;@(negedge clk);start=0;
  wait(done);@(negedge clk);
  if(result!=4||sl||dl||busy)$fatal(1,"Watchdog did not release bus");
  if(cycles-before_cycle<TICK*TIMEOUT||cycles-before_cycle>TICK*TIMEOUT+10)$fatal(1,"Timeout duration changed");
  for(i=0;i<30000;i=i+1)begin
   @(negedge clk);{scl,sda,start,read_op}=($random(seed)&15);addr=$random(seed);wd=$random(seed);
   rst=i%2000==1999;
  end
  @(negedge clk);$display("PASS I2C cycle equivalence: divider=%0d timeout=%0d, exact timeout/released pads, 30000 random clocks, reset",TICK,TIMEOUT);$finish;
 end
 initial begin #((TICK*TIMEOUT+40000)*20);$fatal(1,"I2C timeout");end
endmodule
