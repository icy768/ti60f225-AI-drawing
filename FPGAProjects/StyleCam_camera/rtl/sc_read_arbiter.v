// Two clients, one outstanding AXI read burst. Round-robin at burst boundaries.
// Latch the address before presenting ARVALID so it stays stable under stalls.
module sc_read_arbiter #(parameter DISPLAY_PRIORITY=0)(
 input clk,rst,
 input [31:0] a_addr,input a_valid,output a_ready,
 output a_rvalid,input a_rready,
 input [31:0] b_addr,input b_valid,output b_ready,
 output b_rvalid,input b_rready,
 output reg [31:0] araddr,output arvalid,input arready,
 input rvalid,input rlast,output rready);
 reg [1:0] state;reg owner,last_owner;
 // Camera mode gives HDMI a deadline; its FIFO credit gate leaves replay slots.
 wire choose_b=b_valid&&(!a_valid||(!DISPLAY_PRIORITY&&!last_owner));
 assign arvalid=state==1;
 assign a_ready=(state==1)&&!owner&&arready;
 assign b_ready=(state==1)&&owner&&arready;
 assign a_rvalid=(state==2)&&!owner&&rvalid;
 assign b_rvalid=(state==2)&&owner&&rvalid;
 assign rready=(state==2)&&(owner?b_rready:a_rready);
 always @(posedge clk) begin
  if(rst)begin state<=0;owner<=0;last_owner<=1;araddr<=0;end
  else case(state)
   0:if(a_valid||b_valid)begin owner<=choose_b;araddr<=choose_b?b_addr:a_addr;state<=1;end
   1:if(arready)state<=2;
   2:if(rvalid&&rready&&rlast)begin state<=(DISPLAY_PRIORITY&&!owner)?3:0;last_owner<=owner;end
   // Let the HDMI client queue its next burst after observing RLAST.
   // Without this cycle, continuously queued replay wins before A_VALID rises.
   3:state<=0;
  endcase
 end
endmodule
