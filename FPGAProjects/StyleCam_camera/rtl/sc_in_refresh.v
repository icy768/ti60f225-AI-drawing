// Read frozen statistics, compute coefficients, write only between frames.
module sc_in_refresh #(parameter WIDTH=640,HEIGHT=480,CONSTFILE="model/in_constants.mem",
 COMPACT=1,TRACE=1,PARAMFILE={CONSTFILE,".parameters"},EPSFILE={CONSTFILE,".epsilon"})(
 input clk,rst,start,input [1:0] style,input [3:0] layer,
 output reg busy,done,error,output reg [7:0] stats_index,
 input [39:0] stats_s1,input [59:0] stats_s2,
 output reg cfg_we,output reg [4:0] cfg_layer,output reg [11:0] cfg_addr,output reg [37:0] cfg_data,
 input [9:0] trace_index,output reg [37:0] trace_data,
 output reg [31:0] cycles,output reg [31:0] writes);
 reg [37:0] trace[0:863];
 reg [303:0] word;reg [9:0] address;reg [8:0] epsilon_address;
 reg [3:0] state,saved_layer;reg [1:0] saved_style;reg [7:0] cout;
 wire constants_ready;
 // Thirteen 512x20 ROM banks replace the wide parameter/epsilon tables.
 // Eleven sequential reads per channel are negligible beside the arithmetic;
 // the original 304-bit word is reconstructed without rounding.
 generate if(COMPACT)begin:g_compact
  reg loading,ready,finishing,pipe_valid;
  reg [3:0] read_count,index_q,pbank_q;
  reg [1:0] ebank_q;
  reg [12:0] pbase;
  reg [10:0] ebase;
  reg [119:0] packed_p;
  reg [99:0] packed_e;
  wire [8:0] channel_index=(saved_layer==0?9'd0:9'd16+(saved_layer-1'b1)*9'd24)+stats_index;
  wire [9:0] parameter_index=saved_style*10'd272+channel_index;
  wire [12:0] pa=pbase+read_count;
  wire [10:0] ea=ebase+(read_count-4'd6);
  wire load=busy&&(state==1);
  wire [19:0] pq[0:9],eq[0:2];
  genvar bank;
  for(bank=0;bank<10;bank=bank+1)begin:g_p
   localparam [7:0] DIGIT=8'd48+bank;
   (* syn_ramstyle="block_ram" *) reg [19:0] mem[0:511];
   reg [19:0] q;
   initial $readmemh({CONSTFILE,".p",DIGIT},mem);
   always @(posedge clk)if(loading&&read_count<6&&pa[12:9]==bank)q<=mem[pa[8:0]];
   assign pq[bank]=q;
  end
  for(bank=0;bank<3;bank=bank+1)begin:g_e
   localparam [7:0] DIGIT=8'd48+bank;
   (* syn_ramstyle="block_ram" *) reg [19:0] mem[0:511];
   reg [19:0] q;
   initial $readmemh({CONSTFILE,".e",DIGIT},mem);
   always @(posedge clk)if(loading&&read_count>=6&&read_count<11&&ea[10:9]==bank)q<=mem[ea[8:0]];
   assign eq[bank]=q;
  end
  wire [71:0] gamma_value={{7{packed_p[116]}},packed_p[116:56],4'd0};
  wire [135:0] epsilon_value={8'd0,packed_e[87:0],40'd0};
  assign constants_ready=ready;
  always @(posedge clk)begin
   if(rst||!load)begin loading<=0;ready<=0;finishing<=0;pipe_valid<=0;read_count<=0;end
   else if(!loading&&!ready&&!finishing)begin
    pbase<=parameter_index*13'd6;ebase<=channel_index*11'd5;
    loading<=1;read_count<=0;pipe_valid<=0;
   end else if(loading)begin
    pipe_valid<=read_count<11;index_q<=read_count;pbank_q<=pa[12:9];ebank_q<=ea[10:9];
    if(read_count<11)read_count<=read_count+1'b1;
    if(pipe_valid)begin
     if(index_q<6)packed_p[index_q*20+:20]<=pq[pbank_q];
     else packed_e[(index_q-4'd6)*20+:20]<=eq[ebank_q];
     if(index_q==10)begin loading<=0;finishing<=1;pipe_valid<=0;end
    end
   end else if(finishing)begin
    word<={gamma_value,40'd0,packed_p[55:0],epsilon_value};
    finishing<=0;ready<=1;
   end
  end
 end else begin:g_full
  reg [303:0] constants[0:863];initial $readmemh(CONSTFILE,constants);
  always @(posedge clk)word<=constants[address];
  assign constants_ready=1'b1;
 end endgenerate
 always @(posedge clk)trace_data<=TRACE?trace[trace_index]:38'd0;
 reg math_start;wire math_busy,math_done,math_error;wire [37:0] coefficient;
 wire [18:0] samples=(saved_layer==0||saved_layer>=10)?(WIDTH/2)*(HEIGHT/2):(WIDTH/4)*(HEIGHT/4);
 function [4:0] shift(input [3:0] l);
  case(l) 0:shift=20; 1:shift=21; 2:shift=17; 3:shift=17; 4:shift=19; 5:shift=17; 6:shift=18; 7:shift=17; 8:shift=19; 9:shift=18; 10:shift=20; 11:shift=19; default:shift=0; endcase
 endfunction
 sc_in_math math(.clk(clk),.rst(rst),.start(math_start),.s1(stats_s1),.s2(stats_s2),
 .n(samples),.shift_s(shift(saved_layer)),.gamma_num(word[303:192]),.beta_num(word[191:136]),.eps_num(word[135:0]),
 .busy(math_busy),.done(math_done),.error(math_error),.coefficient(coefficient));
 always @(posedge clk)begin
  cfg_we<=0;done<=0;math_start<=0;
  if(rst)begin busy<=0;done<=0;error<=0;stats_index<=0;state<=0;cycles<=0;writes<=0;address<=0;epsilon_address<=0;end
  else if(start&&!busy)begin
   busy<=1;error<=0;state<=1;saved_layer<=layer;saved_style<=style;stats_index<=0;
   cout<=(layer==0||layer==11)?16:24;address<=style*288+layer*24;epsilon_address<=layer*24;cycles<=0;writes<=0;
   if(layer>=12||style>=3)begin busy<=0;done<=1;error<=1;state<=0;end
  end else if(busy)begin
   cycles<=cycles+1'b1;
   case(state)
    1:if(constants_ready)state<=2;
    2:state<=3;
    3:begin math_start<=1;state<=4;end
    4:if(math_done)begin
     if(math_error)begin error<=1;busy<=0;done<=1;state<=0;end
     else begin
      cfg_layer<=saved_layer;cfg_addr<=saved_style*cout+stats_index;cfg_data<=coefficient;cfg_we<=1;
      if(TRACE)trace[address]<=coefficient;writes<=writes+1'b1;state<=5;
     end
    end
    5:state<=6; // requant writes the low half on the following cycle.
    6:if(stats_index==cout-1)begin busy<=0;done<=1;state<=0;end
      else begin stats_index<=stats_index+1'b1;address<=address+1'b1;epsilon_address<=epsilon_address+1'b1;state<=1;end
    default:begin error<=1;busy<=0;done<=1;state<=0;end
   endcase
  end
 end
endmodule
