// Shared unsigned integer ALU. No combinational multiplier/divider/sqrt.
// op 0: multiply; op 1: divide, nearest ties to even; op 2: floor sqrt.
module sc_in_alu #(parameter W=160)(
 input clk,rst,start,input [1:0] op,input [W-1:0] a,b,
 output reg busy,done,error,output reg [W-1:0] result);
 reg [1:0] mode;
 reg [W-1:0] x,y,q;
 reg [W:0] rem;
 reg [8:0] count;
 wire [W:0] shifted=(mode==2)?((rem<<2)|x[W-1:W-2]):((rem<<1)|x[W-1]);
 wire [W:0] trial=(mode==2)?(({1'b0,q}<<2)|1'b1):{1'b0,y};
 wire [W:0] difference=shifted-trial;
 wire ge=shifted>=trial;
 wire [W:0] twice_rem=rem<<1;
 wire increment=(twice_rem>{1'b0,y})||((twice_rem=={1'b0,y})&&q[0]);
 always @(posedge clk) begin
  done<=0;
  if(rst)begin busy<=0;done<=0;error<=0;result<=0;end
  else if(start&&!busy)begin
   mode<=op;x<=a;y<=b;q<=0;rem<=0;error<=0;busy<=1;
   count<=(op==2)?W/2:W;
   if(op==1&&b==0)begin error<=1;result<=0;busy<=0;done<=1;end
  end else if(busy)case(mode)
   0:if(y==0)begin result<=rem[W-1:0];busy<=0;done<=1;end
     else begin if(y[0])rem<=rem+{1'b0,x};x<=x<<1;y<=y>>1;end
   1:if(count==0)begin result<=q+increment;busy<=0;done<=1;end
     else begin rem<=ge?difference:shifted;q<=(q<<1)|ge;x<=x<<1;count<=count-1'b1;end
   2:if(count==0)begin result<=q;busy<=0;done<=1;end
     else begin rem<=ge?difference:shifted;q<=(q<<1)|ge;x<=x<<2;count<=count-1'b1;end
   default:begin busy<=0;done<=1;error<=1;end
  endcase
 end
endmodule
