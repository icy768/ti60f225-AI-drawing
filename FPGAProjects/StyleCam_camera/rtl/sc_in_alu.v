// Exact word-serial arithmetic for dynamic IN. One local carry chain and one
// word-written result/remainder bank replace separate remainder/partial/Q banks.
// 0 unsigned multiply modulo 2^W, 1 unsigned divide RNE, 2 floor sqrt,
// 3 add, 4 subtract (borrow), 5 unsigned right shift RNE by b[7:0].
// result is valid with done; its intermediate contents may change while busy.
module sc_in_alu #(parameter W=160, WORD=16)(
 input clk,rst,start,input [2:0] op,input [W-1:0] a,b,
 output reg busy,done,error,output [W-1:0] result,output reg borrow);
 localparam NW=(W+1+WORD-1)/WORD,P=NW*WORD;
 localparam PREP=0,WORDS=1,SHIFT=2;
 localparam STEP=0,RESTORE=1,COMPARE=2,INCREMENT=3,DIRECT=4;
 reg [1:0] state;reg [2:0] phase,mode;
 reg [W-1:0] x,y;
 reg [WORD-1:0] work[0:NW-1];
 wire [P-1:0] packed_work;
 reg carry,negative,nonzero,guard,sticky;
 reg [1:0] shift_bits;
 reg [8:0] count;
 reg [$clog2(NW+1)-1:0] limb;
 wire command=start&&!busy&&!rst;
 wire [P-1:0] px={{(P-W){1'b0}},x},py={{(P-W){1'b0}},y};
 wire [WORD-1:0] current_word=work[limb];
 wire [WORD-1:0] x_word=px[limb*WORD+:WORD];
 wire [WORD-1:0] y_word=py[limb*WORD+:WORD];
 wire [P-1:0] trial_y=py<<2;
 wire [WORD-1:0] sqrt_trial=trial_y[limb*WORD+:WORD]|
   ((limb==0)?(negative?{{(WORD-2){1'b0}},2'b11}:{{(WORD-1){1'b0}},1'b1}):{WORD{1'b0}});
 wire shifted_left=(phase==COMPARE)||(phase==STEP&&(mode==1||mode==2));
 wire two_bits=phase==STEP&&mode==2;
 wire [WORD-1:0] left=shifted_left?
   (two_bits?((current_word<<2)|shift_bits):((current_word<<1)|shift_bits[0])):current_word;
 wire [WORD-1:0] right=(phase==INCREMENT)?{WORD{1'b0}}:
   (phase==STEP&&mode==0)?x_word:(phase==STEP&&mode==2)?sqrt_trial:y_word;
 wire subtract=(phase==COMPARE)||(phase==DIRECT&&mode==4)||
   (phase==STEP&&(mode==1||mode==2)&&!negative);
 wire [WORD:0] sum={1'b0,left}+{1'b0,(right^{WORD{subtract}})}+carry;
 wire last_word=limb==NW-1;
 wire round_up=sum[WORD]&&(nonzero||(|sum[WORD-1:0])||x[0]);
 wire finish_compare=busy&&state==WORDS&&last_word&&phase==COMPARE;
 wire finish_sqrt=busy&&state==PREP&&mode==2&&count==0;
 genvar k;
 generate for(k=0;k<NW;k=k+1)begin:g_word
  assign packed_work[k*WORD+:WORD]=work[k];
  // Division reuses x for the consumed dividend and emerging quotient;
  // sqrt reuses y for its root. Both use only this word-written remainder.
  always @(posedge clk)begin
   if(rst)work[k]<=0;
   else if(command&&op<=2)work[k]<=0;
   else if(command&&op>=3&&op<=5)work[k]<={{(P-W){1'b0}},a}>>(k*WORD);
   else if(finish_compare)work[k]<=px[k*WORD+:WORD];
   else if(finish_sqrt)work[k]<=py[k*WORD+:WORD];
   else if(busy&&state==SHIFT&&count!=0)begin
    if(k==NW-1)work[k]<={1'b0,work[k][WORD-1:1]};
    else work[k]<={work[k+1][0],work[k][WORD-1:1]};
   end else if(busy&&state==WORDS&&limb==k)work[k]<=sum[WORD-1:0];
  end
 end endgenerate
 assign result=packed_work[W-1:0];
 always @(posedge clk)begin
  done<=0;
  if(rst)begin busy<=0;done<=0;error<=0;borrow<=0;state<=PREP;end
  else if(command)begin
   mode<=op;x<=a;y<=op==2?{W{1'b0}}:b;
   error<=0;borrow<=0;busy<=1;negative<=0;
   count<=op==2?W/2:W;state<=PREP;phase<=STEP;
   if(op==1&&b==0)begin busy<=0;done<=1;error<=1;end
   else if(op==3||op==4)begin
    carry<=op==4;limb<=0;phase<=DIRECT;state<=WORDS;nonzero<=0;
   end else if(op==5)begin count<=b[7:0];guard<=0;sticky<=0;state<=SHIFT;end
   else if(op>5)begin busy<=0;done<=1;error<=1;end
  end else if(busy)case(state)
   PREP:begin
    if(mode==0)begin
     if(y==0)begin busy<=0;done<=1;end
     else if(!y[0])begin x<=x<<1;y<=y>>1;end
     else begin carry<=0;limb<=0;phase<=STEP;state<=WORDS;end
    end else if(count==0)begin
     if(mode==2)begin busy<=0;done<=1;end
     else begin
      limb<=0;nonzero<=0;shift_bits<=0;state<=WORDS;
      if(negative)begin phase<=RESTORE;carry<=0;end
      else begin phase<=COMPARE;carry<=1;end
     end
    end else begin
     // Non-restoring divide/sqrt retain every remainder; its sign selects
     // the following add/subtract, avoiding a full-width shadow bank.
     carry<=!negative;limb<=0;phase<=STEP;state<=WORDS;
     shift_bits<=mode==2?x[W-1:W-2]:{1'b0,x[W-1]};
    end
   end
   WORDS:begin
    carry<=sum[WORD];nonzero<=nonzero||(|sum[WORD-1:0]);limb<=limb+1'b1;
    shift_bits<=two_bits?current_word[WORD-1:WORD-2]:{1'b0,current_word[WORD-1]};
    if(last_word)case(phase)
     DIRECT:begin borrow<=subtract&&!sum[WORD];busy<=0;done<=1;end
     INCREMENT:begin busy<=0;done<=1;end
     RESTORE:begin phase<=COMPARE;carry<=1;limb<=0;nonzero<=0;shift_bits<=0;negative<=0;end
     COMPARE:begin
      if(round_up)begin phase<=INCREMENT;carry<=1;limb<=0;end
      else begin busy<=0;done<=1;end
     end
     default:begin
      if(mode==0)begin x<=x<<1;y<=y>>1;end
      else if(mode==1)begin x<=(x<<1)|!sum[WORD-1];negative<=sum[WORD-1];count<=count-1'b1;end
      else begin x<=x<<2;y<=(y<<1)|!sum[WORD-1];negative<=sum[WORD-1];count<=count-1'b1;end
      state<=PREP;
     end
    endcase
   end
   SHIFT:begin
    if(count!=0)begin sticky<=sticky||guard;guard<=work[0][0];count<=count-1'b1;end
    else if(guard&&(sticky||work[0][0]))begin carry<=1;limb<=0;phase<=INCREMENT;state<=WORDS;end
    else begin busy<=0;done<=1;end
   end
   default:begin error<=1;busy<=0;done<=1;end
  endcase
 end
endmodule
