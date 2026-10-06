// Active-low input: synchronize, debounce both edges, pulse once per press.
module sc_button #(parameter CYCLES=250000)(
 input clk,input rst,input key_n,output reg press,output reg released);
 localparam CW=(CYCLES>1)?$clog2(CYCLES):1;
 (* async_reg="true" *) reg sync1,sync2;
 reg [CW-1:0] count;
 always @(posedge clk)begin
  if(rst)begin sync1<=1;sync2<=1;released<=1;count<=0;press<=0;end
  else begin
   sync1<=key_n;sync2<=sync1;press<=0;
   if(sync2==released)count<=0;
   else if(count==CYCLES-1)begin
    released<=sync2;count<=0;press<=!sync2;
   end else count<=count+1'b1;
  end
 end
endmodule
