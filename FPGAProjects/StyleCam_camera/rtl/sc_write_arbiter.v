// Round-robin ownership of an entire single-beat AXI AW/W/B transaction.
module sc_write_arbiter(
 input clk,rst,
 input [31:0] a_addr,input a_av,output a_ar,input [127:0] a_data,input a_wv,output a_wr,output a_bv,input a_br,
 input [31:0] b_addr,input b_av,output b_ar,input [127:0] b_data,input b_wv,output b_wr,output b_bv,input b_br,
 output [31:0] awaddr,output awvalid,input awready,output [127:0] wdata,output wvalid,input wready,input bvalid,output bready);
 reg owner,active,next_owner;
 assign awaddr=owner?b_addr:a_addr;assign awvalid=active&&(owner?b_av:a_av);
 assign wdata=owner?b_data:a_data;assign wvalid=active&&(owner?b_wv:a_wv);
 assign bready=active&&(owner?b_br:a_br);
 assign a_ar=active&&!owner&&awready;assign b_ar=active&&owner&&awready;
 assign a_wr=active&&!owner&&wready;assign b_wr=active&&owner&&wready;
 assign a_bv=active&&!owner&&bvalid;assign b_bv=active&&owner&&bvalid;
 always @(posedge clk)begin
  if(rst)begin active<=0;owner<=0;next_owner<=0;end
  else if(!active&&(a_av||b_av))begin active<=1;owner<=(a_av&&b_av)?next_owner:b_av;end
  else if(active&&bvalid&&bready)begin active<=0;next_owner<=!owner;end
 end
endmodule
