module uart_byte #(parameter DIV=27)(input clk,input rst,input rx,output reg tx=1,
 output reg [7:0] rx_data,output reg rx_valid,output reg rx_error,
 input [7:0] tx_data,input tx_valid,output tx_ready,output rx_busy);
 (* async_reg="true" *) reg rx_meta=1,rx_sync=1;
 always @(posedge clk) begin rx_meta<=rx; rx_sync<=rx_meta; end
 reg [15:0] rc; reg [3:0] rb; reg [7:0] rd; reg receiving;
 assign rx_busy=receiving||!rx_sync;
 reg [15:0] tc; reg [3:0] tb; reg [9:0] td;
 assign tx_ready=(tb==0);
 always @(posedge clk) begin
  rx_valid<=0; rx_error<=0;
  if(rst) begin rc<=0; rb<=0; receiving<=0; tc<=0; tb<=0; tx<=1; end
  else begin
   if(!receiving) begin
    if(!rx_sync) begin receiving<=1; rc<=DIV/2; rb<=0; end
   end else if(rc!=0) rc<=rc-1'b1;
   else begin
    rc<=DIV-1;
    if(rb==0) begin if(rx_sync) receiving<=0; else rb<=1; end
    else if(rb<=8) begin rd[rb-1]<=rx_sync; rb<=rb+1'b1; end
    else begin receiving<=0; rx_data<=rd; rx_valid<=rx_sync; rx_error<=!rx_sync; end
   end
   if(tb==0) begin
    tx<=1;
    if(tx_valid) begin td<={1'b1,tx_data,1'b0}; tx<=0; tb<=10; tc<=DIV-1; end
   end else if(tc!=0) tc<=tc-1'b1;
   else begin tc<=DIV-1; td<={1'b1,td[9:1]}; tx<=td[1]; tb<=tb-1'b1; end
  end
 end
endmodule
