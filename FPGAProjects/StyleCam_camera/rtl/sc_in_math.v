// Q40 IN arithmetic. Constants are computed from trained model scales only.
// gamma_num = round(gamma/s_y * 2^40) * N * 2^40 (signed).
// eps_num = round(eps/(s_x*s_w*2^R)^2 * N^2 * 2^80).
module sc_in_math(
 input clk,rst,start,input signed [39:0] s1,input [59:0] s2,
 input [18:0] n,input [4:0] shift_s,
 input signed [111:0] gamma_num,input signed [55:0] beta_num,input [135:0] eps_num,
 output reg busy,done,error,output reg [37:0] coefficient);
 reg [4:0] state;
 reg [39:0] mean_abs;reg mean_neg,gamma_neg;
 reg [18:0] samples;reg [4:0] scale_shift;
 reg [159:0] squares,square_sum,epsilon,gnum,beta,gain;
 reg signed [17:0] m;
 reg start_alu;reg [1:0] op;reg [159:0] a,b;
 wire alu_busy,alu_done,alu_error;wire [159:0] result;
 sc_in_alu alu(clk,rst,start_alu,op,a,b,alu_busy,alu_done,alu_error,result);
 wire signed [160:0] b_value=gamma_neg^mean_neg?$signed({1'b0,result}):-$signed({1'b0,result});
 wire signed [160:0] bias_sum=$signed({beta[159],beta})+b_value;
 wire signed [160:0] b_final=beta[159]?-$signed({1'b0,result})+161'sd128:$signed({1'b0,result})+161'sd128;
 always @(posedge clk)begin
  done<=0;start_alu<=0;
  if(rst)begin busy<=0;done<=0;error<=0;state<=0;coefficient<=0;end
  else if(start&&!busy)begin
   busy<=1;error<=0;state<=1;
   mean_abs<=s1[39]?-s1:s1;mean_neg<=s1[39];gamma_neg<=gamma_num[111];
   samples<=n;scale_shift<=shift_s;square_sum<={{100{1'b0}},s2};
   epsilon<={{24{1'b0}},eps_num};gnum<=gamma_num[111]?-gamma_num:gamma_num;
   beta<={{104{beta_num[55]}},beta_num};
   if(n==0||shift_s>40)begin busy<=0;done<=1;error<=1;state<=0;end
  end else if(busy)begin
   if(alu_done&&alu_error)begin error<=1;busy<=0;done<=1;state<=0;end
   else case(state)
    1:begin op<=0;a<=mean_abs;b<=mean_abs;start_alu<=1;state<=2;end
    2:if(alu_done)begin squares<=result;state<=3;end
    3:begin op<=0;a<=square_sum;b<=samples;start_alu<=1;state<=4;end
    4:if(alu_done)begin square_sum<=result;state<=5;end
    5:begin op<=2;a<=((square_sum>=squares?square_sum-squares:160'd0)<<80)+epsilon;b<=0;start_alu<=1;state<=6;end
    6:if(alu_done)begin op<=1;a<=gnum;b<=result;start_alu<=1;state<=7;end
    7:if(alu_done)begin gain<=result;state<=8;end
    8:begin op<=1;a<=gain;b<=160'd1<<(40-scale_shift);start_alu<=1;state<=9;end
    9:if(alu_done)begin
     if(gamma_neg)m<=result>=131072?-18'sd131072:-$signed(result[17:0]);
     else m<=result>131071?18'sd131071:result[17:0];
     state<=10;
    end
    10:begin op<=0;a<=gain;b<=mean_abs;start_alu<=1;state<=11;end
    11:if(alu_done)begin op<=1;a<=result<<8;b<=samples;start_alu<=1;state<=12;end
    12:if(alu_done)begin beta<=bias_sum[159:0];state<=13;end
    13:begin op<=1;a<=beta[159]?-$signed(beta):beta;b<=160'd1<<40;start_alu<=1;state<=14;end
    14:if(alu_done)begin
     coefficient[37:20]<=m;
     coefficient[19:0]<=b_final>524287?20'sd524287:(b_final< -524288?-20'sd524288:b_final[19:0]);
     busy<=0;done<=1;state<=0;
    end
    default:begin error<=1;busy<=0;done<=1;state<=0;end
   endcase
  end
 end
endmodule
