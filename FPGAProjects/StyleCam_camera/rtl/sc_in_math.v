// Exact Q40 IN coefficients. Command operands feed the ALU input registers
// directly; gamma storage is reused for gain once the divide has completed.
module sc_in_math(
 input clk,rst,start,input signed [39:0] s1,input [59:0] s2,
 input [18:0] n,input [4:0] shift_s,
 input signed [111:0] gamma_num,input signed [55:0] beta_num,input [135:0] eps_num,
 output reg busy,done,error,output reg [37:0] coefficient);
 reg [4:0] state;
 reg [39:0] mean_abs;reg mean_neg,gamma_neg;
 reg [18:0] samples;reg [4:0] scale_shift;
 reg [79:0] squares;reg [59:0] square_sum;
 reg [135:0] epsilon;
 reg [111:0] gain;
 reg [55:0] beta;reg bias_neg;
 reg signed [17:0] m;
 reg start_alu;reg [2:0] op;reg [159:0] a,b;
 wire alu_busy,alu_done,alu_error,alu_borrow;wire [159:0] result;
 sc_in_alu alu(clk,rst,start_alu,op,a,b,alu_busy,alu_done,alu_error,result,alu_borrow);
 // The ALU captures operands on the command edge, so no second 160-bit
 // operand register bank is needed in this controller.
 always @* begin
  start_alu=0;op=0;a=0;b=0;
  if(busy&&!rst&&!(alu_done&&alu_error))case(state)
   1:begin start_alu=1;op=0;a=mean_abs;b=mean_abs;end
   3:begin start_alu=1;op=0;a=square_sum;b=samples;end
   4:if(alu_done)begin start_alu=1;op=4;a=result[79:0];b=squares;end
   15:if(alu_done)begin start_alu=1;op=3;a=alu_borrow?160'd0:{result[79:0],80'd0};b=epsilon;end
   16:if(alu_done)begin start_alu=1;op=2;a=result;end
   6:if(alu_done)begin start_alu=1;op=1;a=gain;b=result;end
   8:begin start_alu=1;op=5;a=gain;b=40-scale_shift;end
   10:begin start_alu=1;op=0;a=gain;b=mean_abs;end
   11:if(alu_done)begin start_alu=1;op=1;a=result<<8;b=samples;end
   12:if(alu_done)begin start_alu=1;op=(gamma_neg^mean_neg)?3:4;a={{104{beta[55]}},beta};b=result;end
   17:if(alu_done)begin start_alu=1;op=result[159]?4:5;a=result[159]?160'd0:result;b=result[159]?result:160'd40;end
   18:if(alu_done)begin start_alu=1;op=5;a=result;b=40;end
  endcase
 end
 always @(posedge clk)begin
  done<=0;
  if(rst)begin busy<=0;done<=0;error<=0;state<=0;coefficient<=0;end
  else if(start&&!busy)begin
   busy<=1;error<=0;state<=1;
   mean_abs<=s1[39]?-s1:s1;mean_neg<=s1[39];gamma_neg<=gamma_num[111];
   samples<=n;scale_shift<=shift_s;square_sum<=s2;
   epsilon<=eps_num;gain<=gamma_num[111]?-gamma_num:gamma_num;
   beta<=beta_num;
   if(n==0)begin busy<=0;done<=1;error<=1;state<=0;end
  end else if(busy)begin
   if(alu_done&&alu_error)begin error<=1;busy<=0;done<=1;state<=0;end
   else case(state)
    1:state<=2;
    2:if(alu_done)begin squares<=result[79:0];state<=3;end
    3:state<=4;
    4:if(alu_done)state<=15;
    15:if(alu_done)state<=16;
    16:if(alu_done)state<=6;
    6:if(alu_done)state<=7;
    7:if(alu_done)begin gain<=result[111:0];state<=8;end
    8:state<=9;
    9:if(alu_done)begin
     if(gamma_neg)m<=result>=131072?-18'sd131072:-$signed(result[17:0]);
     else m<=result>131071?18'sd131071:result[17:0];
     state<=10;
    end
    10:state<=11;
    11:if(alu_done)state<=12;
    12:if(alu_done)state<=17;
    17:if(alu_done)begin bias_neg<=result[159];state<=result[159]?18:14;end
    18:if(alu_done)state<=14;
    14:if(alu_done)begin
     coefficient[37:20]<=m;
     if(bias_neg)coefficient[19:0]<=result>524416?20'h80000:20'd128-result[19:0];
     else coefficient[19:0]<=result>524159?20'h7ffff:20'd128+result[19:0];
     busy<=0;done<=1;state<=0;
    end
    default:begin error<=1;busy<=0;done<=1;state<=0;end
   endcase
  end
 end
endmodule
