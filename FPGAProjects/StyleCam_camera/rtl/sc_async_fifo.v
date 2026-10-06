// Gray-pointer asynchronous FIFO, synchronous RAM read with one output holding register.
module sc_async_fifo #(parameter W=128,AW=8)(
 input wc,input wrst,input [W-1:0] wd,input wv,output wready,
 input rc,input rrst,output reg [W-1:0] rd,output reg rv,input rready,
 output [AW:0] wlevel);
 reg [W-1:0] mem[0:(1<<AW)-1];
 reg [AW:0] wb,wg,rb,rg;
 (* async_reg="true" *) reg [AW:0] rg1,rg2,wg1,wg2;
 reg [AW:0] read_binary;integer k;
 always @*begin
  read_binary[AW]=rg2[AW];
  for(k=AW-1;k>=0;k=k-1)read_binary[k]=read_binary[k+1]^rg2[k];
 end
 // Conservative write-domain occupancy; the prefetched output is outside RAM.
 assign wlevel=wb-read_binary;
 wire full=wg=={~rg2[AW:AW-1],rg2[AW-2:0]};
 wire empty=rg==wg2;
 assign wready=!full&&!wrst;
 wire [AW:0] wn=wb+1'b1,rn=rb+1'b1;
 always @(posedge wc) begin
  if(wrst) begin wb<=0;wg<=0;rg1<=0;rg2<=0;end
  else begin
   rg1<=rg;rg2<=rg1;
   if(wv&&wready) begin mem[wb[AW-1:0]]<=wd;wb<=wn;wg<=(wn>>1)^wn;end
  end
 end
 always @(posedge rc) begin
  if(rrst) begin rb<=0;rg<=0;wg1<=0;wg2<=0;rv<=0;end
  else begin
   wg1<=wg;wg2<=wg1;
   if(!rv||rready) begin
    rv<=!empty;
    if(!empty) begin rd<=mem[rb[AW-1:0]];rb<=rn;rg<=(rn>>1)^rn;end
   end
  end
 end
endmodule
