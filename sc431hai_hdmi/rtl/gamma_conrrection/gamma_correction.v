// Encode linear camera RGB for a display with nominal gamma 2.2.
// Initialized synchronous ROM reads: no runtime table copy or warm-up period.
module gamma_correction #(
 parameter DATA_WIDTH=10,
 parameter GAMMA_CURVE="./rtl/gamma_conrrection/linear_to_display_2p2.mem"
)(
 input wire i_pclk,i_rstn,i_valid,i_hs,i_vs,
 input wire [DATA_WIDTH-1:0] i_red,i_green,i_blue,
 output reg [DATA_WIDTH-1:0] o_red,o_green,o_blue,
 output reg o_valid,o_hs,o_vs
);
 reg [9:0] curve[0:1023];
 initial $readmemh(GAMMA_CURVE,curve);
 wire [9:0] ar,ag,ab;
 generate if(DATA_WIDTH==10) begin
   assign ar=i_red;assign ag=i_green;assign ab=i_blue;
 end else begin
   assign ar={i_red,i_red[7:6]};
   assign ag={i_green,i_green[7:6]};
   assign ab={i_blue,i_blue[7:6]};
 end endgenerate
 always @(posedge i_pclk) begin
   if(!i_rstn) begin
     o_red<=0;o_green<=0;o_blue<=0;o_valid<=0;o_hs<=0;o_vs<=0;
   end else begin
     o_valid<=i_valid;o_hs<=i_hs;o_vs<=i_vs;
     if(i_valid) begin
       o_red<=curve[ar] >> (10-DATA_WIDTH);
       o_green<=curve[ag] >> (10-DATA_WIDTH);
       o_blue<=curve[ab] >> (10-DATA_WIDTH);
     end else begin o_red<=0;o_green<=0;o_blue<=0;end
   end
 end
endmodule
