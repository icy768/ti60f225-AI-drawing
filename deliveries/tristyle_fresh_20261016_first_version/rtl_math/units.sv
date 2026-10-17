// Arithmetic contract reference only. No synthesis, DSP mapping or frequency claim.
module rne_shift64(input wire signed [63:0] x, input wire signed [8:0] sh,
                   output reg signed [63:0] y);
  reg signed [63:0] q,remn,half;
  always_comb begin
    q=0; remn=0; half=0;
    if (sh<=0) y=x<<<(-sh);
    else if (sh>=64) y=0;
    else begin
      q=x>>>sh; remn=x-(q<<<sh); half=64'sd1<<<(sh-1);
      y=q+((remn>half)||((remn==half)&&q[0]));
    end
  end
endmodule

module mac_dot8(input wire clk,rst,clear,valid,
 input wire [7:0] x,zin,input wire signed [7:0] w,
 input wire signed [31:0] bias,output reg signed [31:0] acc,
 output reg overflow);
 wire signed [8:0] centered=$signed({1'b0,x})-$signed({1'b0,zin});
 wire signed [16:0] product=centered*w;
 wire signed [32:0] next_acc=$signed({acc[31],acc})+{{16{product[16]}},product};
 always @(posedge clk) begin
   if(rst) begin acc<=0;overflow<=0;end
   else if(clear) begin acc<=bias;overflow<=0;end
   else if(valid) begin acc<=next_acc[31:0];overflow<=overflow|(next_acc[32]!=next_acc[31]);end
 end
endmodule

module requant32(input wire signed [31:0] acc,mult,
 input wire signed [7:0] exponent,input wire [7:0] zout,
 input wire relu,output reg [7:0] y);
 wire signed [63:0] product=$signed(acc)*$signed(mult);
 wire signed [8:0] sh=9'sd31-$signed(exponent);
 wire signed [63:0] rounded;
 reg signed [63:0] shifted;
 rne_shift64 r(product,sh,rounded);
 always_comb begin
   shifted=rounded+$signed({1'b0,zout});
   if(shifted<0)y=0;
   else if(shifted>255)y=255;
   else y=shifted[7:0];
   if(relu && y<zout)y=zout;
 end
endmodule

// Same add/cat scalar contract: Q31 input rescale with16 guard bits, then RNE16.
module merge_requant8(input wire [7:0] a,b,za,zb,zo,
 input wire signed [31:0] ma,mb,input wire signed [7:0] ea,eb,
 input wire use_b,output reg [7:0] y);
 wire signed [8:0] da=$signed({1'b0,a})-$signed({1'b0,za});
 wire signed [8:0] db=$signed({1'b0,b})-$signed({1'b0,zb});
 wire signed [63:0] pa=$signed(da)*$signed(ma),pb=$signed(db)*$signed(mb);
 wire signed [8:0] sha=9'sd31-$signed(ea),shb=9'sd31-$signed(eb);
 wire signed [63:0] ra,rb;
 wire signed [63:0] sum=ra+(use_b ? rb:64'sd0);
 wire signed [63:0] result;
 reg signed [63:0] shifted;
 rne_shift64 r0(pa,sha,ra),r1(pb,shb,rb),r2(sum,9'sd16,result);
 always_comb begin
   shifted=result+$signed({1'b0,zo});
   if(shifted<0)y=0;else if(shifted>255)y=255;else y=shifted[7:0];
 end
endmodule
