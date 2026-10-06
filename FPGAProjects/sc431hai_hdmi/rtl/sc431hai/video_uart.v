// Ten 32-bit hexadecimal fields, MSW first: "SCV1 xxxxxxxx ...\r\n".
module video_uart #(parameter integer CYCLES=217, parameter [31:0] MAGIC="SCV1")(
 input wire clk,reset,start,
 input wire [319:0] words,
 output wire tx,
 output reg busy
);
 reg [319:0] captured;
 reg [6:0] pos;
 reg [3:0] digit;
 reg [7:0] character;
 reg launch;
 reg [1:0] state;
 wire tx_busy;
 function [7:0] hexchar;
   input [3:0] v;
   begin hexchar=v<10?8'h30+v:8'h41+v-10;end
 endfunction
 always @* begin
   digit=0;character=" ";
   if(pos<5) case(pos)
     0:character=MAGIC[31:24];1:character=MAGIC[23:16];2:character=MAGIC[15:8];3:character=MAGIC[7:0];4:character=" ";
   endcase
   else if(pos==94) character=13;
   else if(pos==95) character=10;
   else if((pos-5)%9!=8) begin
     digit=captured[319-(((pos-5)/9)*8+(pos-5)%9)*4 -: 4];
     character=hexchar(digit);
   end
 end
 probe_uart_tx #(.CYCLES(CYCLES)) byte_tx(.clk(clk),.reset(reset),.start(launch),
   .data(character),.tx(tx),.busy(tx_busy));
 always @(posedge clk) begin
   if(reset) begin captured<=0;pos<=0;launch<=0;state<=0;busy<=0;end
   else begin
     launch<=0;
     if(!busy) begin
       if(start) begin captured<=words;pos<=0;state<=0;busy<=1;end
     end else case(state)
       0:if(!tx_busy) begin launch<=1;state<=1;end
       1:if(tx_busy) state<=2;
       2:if(!tx_busy) begin
         if(pos==95) busy<=0;
         else begin pos<=pos+1'b1;state<=0;end
       end
     endcase
   end
 end
endmodule

module probe_uart_tx #(parameter integer CYCLES=217)(
    input wire clk, reset, start,
    input wire [7:0] data,
    output wire tx,
    output reg busy
);
    reg [9:0] shift;
    reg [15:0] counter;
    reg [3:0] bits_left;
    assign tx = busy ? shift[0] : 1'b1;
    always @(posedge clk) begin
        if(reset) begin busy<=0; shift<=10'h3ff; counter<=0; bits_left<=0; end
        else if(!busy) begin
            if(start) begin
                shift<={1'b1,data,1'b0}; busy<=1; counter<=0; bits_left<=10;
            end
        end else if(counter==CYCLES-1) begin
            counter<=0; shift<={1'b1,shift[9:1]}; bits_left<=bits_left-1'b1;
            if(bits_left==1) busy<=0;
        end else counter<=counter+1'b1;
    end
endmodule
