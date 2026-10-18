// Word-serial unsigned ALU: one WORD-bit carry chain for all arithmetic.
// 0 multiply modulo 2^W, 1 divide RNE, 2 floor sqrt, 3 add, 4 subtract,
// 5 right shift by b[7:0] with round-to-nearest/ties-to-even.
module sc_in_alu_resource3 #(parameter W=160, WORD=16)(
 input clk,rst,start,input [2:0] op,input [W-1:0] a,b,
 output reg busy,done,error,output reg [W-1:0] result,output reg borrow);
 localparam NW=(W+1+WORD-1)/WORD, P=NW*WORD;
 localparam PREP=0,WORDS=1,SHIFT=2;
 localparam STEP=0,ROUND_CMP=1,ROUND_INC=2,DIRECT=3;
 reg [1:0] state,phase;
 reg [2:0] mode;
 reg [W-1:0] x,y,q;
 reg [W:0] rem;
 reg [P-1:0] partial;
 reg carry,nonzero,guard,sticky;
 reg [8:0] count;
 reg [$clog2(NW+1)-1:0] limb;
 wire [W:0] shifted=(mode==2)?((rem<<2)|x[W-1:W-2]):((rem<<1)|x[W-1]);
 wire [W:0] trial=(mode==2)?(({1'b0,q}<<2)|1'b1):{1'b0,y};
 // Index fixed words instead of rotating two full-width working operands.
 wire [P-1:0] left_word_source=(phase==DIRECT)?{{(P-W){1'b0}},x}:
   (phase==ROUND_CMP)?{{(P-W-2){1'b0}},rem,1'b0}:
   (phase==ROUND_INC)?{{(P-W){1'b0}},(mode==5?x:q)}:
   (mode==0)?{{(P-W-1){1'b0}},rem}:{{(P-W-1){1'b0}},shifted};
 wire [P-1:0] right_word_source=(phase==ROUND_INC)?{{(P-1){1'b0}},1'b1}:
   (phase==DIRECT||phase==ROUND_CMP)?{{(P-W){1'b0}},y}:
   (mode==0)?{{(P-W){1'b0}},x}:{{(P-W-1){1'b0}},trial};
 wire subtract=(phase==ROUND_CMP)||(phase==DIRECT&&mode==4)||(phase==STEP&&mode!=0);
 wire [WORD-1:0] left_limb=left_word_source[limb*WORD+:WORD];
 wire [WORD-1:0] right_limb=right_word_source[limb*WORD+:WORD];
 wire [WORD:0] sum={1'b0,left_limb}+{1'b0,(right_limb^{WORD{subtract}})}+carry;
 wire [P-1:0] completed={sum[WORD-1:0],partial[P-WORD-1:0]};
 wire round_up=sum[WORD]&&(nonzero||(|sum[WORD-1:0])||q[0]);
 genvar k;
 generate for(k=0;k<NW;k=k+1)begin:g_word
  always @(posedge clk)if(busy&&state==WORDS&&limb==k)partial[k*WORD+:WORD]<=sum[WORD-1:0];
 end endgenerate
 always @(posedge clk)begin
  done<=0;
  if(rst)begin busy<=0;done<=0;error<=0;result<=0;borrow<=0;state<=PREP;end
  else if(start&&!busy)begin
   mode<=op;x<=a;y<=b;q<=0;rem<=0;error<=0;borrow<=0;busy<=1;
   count<=(op==2)?W/2:W;state<=PREP;
   if(op==1&&b==0)begin error<=1;result<=0;busy<=0;done<=1;end
   else if(op==3||op==4)begin
    carry<=op==4;
    limb<=0;phase<=DIRECT;state<=WORDS;nonzero<=0;
   end else if(op==5)begin count<=b[7:0];guard<=0;sticky<=0;state<=SHIFT;end
   else if(op>5)begin error<=1;busy<=0;done<=1;end
  end else if(busy)case(state)
   PREP:begin
    if(mode==0)begin
     if(y==0)begin result<=rem[W-1:0];busy<=0;done<=1;end
     else if(!y[0])begin x<=x<<1;y<=y>>1;end
     else begin carry<=0;limb<=0;phase<=STEP;state<=WORDS;end
    end else if(count==0)begin
     if(mode==2)begin result<=q;busy<=0;done<=1;end
     else begin carry<=1;limb<=0;nonzero<=0;phase<=ROUND_CMP;state<=WORDS;end
    end else begin carry<=1;limb<=0;phase<=STEP;state<=WORDS;end
   end
   WORDS:begin
    carry<=sum[WORD];
    nonzero<=nonzero||(|sum[WORD-1:0]);limb<=limb+1'b1;
    if(limb==NW-1)begin
     case(phase)
      DIRECT:begin result<=completed[W-1:0];borrow<=subtract&&!sum[WORD];busy<=0;done<=1;end
      ROUND_INC:begin result<=completed[W-1:0];busy<=0;done<=1;end
      ROUND_CMP:begin
       if(round_up)begin carry<=0;limb<=0;phase<=ROUND_INC;end
       else begin result<=q;busy<=0;done<=1;end
      end
      default:begin
       if(mode==0)begin rem<=completed[W:0];x<=x<<1;y<=y>>1;end
       else begin rem<=sum[WORD]?completed[W:0]:shifted;q<=(q<<1)|sum[WORD];x<=mode==2?x<<2:x<<1;count<=count-1'b1;end
       state<=PREP;
      end
     endcase
    end
   end
   SHIFT:begin
    if(count!=0)begin x<=x>>1;sticky<=sticky||guard;guard<=x[0];count<=count-1'b1;end
    else if(guard&&(sticky||x[0]))begin carry<=0;limb<=0;phase<=ROUND_INC;state<=WORDS;end
    else begin result<=x;busy<=0;done<=1;end
   end
   default:begin error<=1;busy<=0;done<=1;end
  endcase
 end
endmodule
