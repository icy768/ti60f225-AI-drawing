`timescale 1ns/1ps
module diagnostics_tb;
 reg clk=0,src=0,run_src=1,reset=1;
 always #5 clk=~clk;
 always #7 if(run_src) src=~src;
 reg vs=0,de=0,irq=0;
 reg [1:0] vc=0;
 reg [5:0] dt=6'h2b;
 reg [15:0] wc=10;
 reg [3:0] ppc=4;
 wire [223:0] values;
 sc_frame_stats #(.FRAME_PIXELS(16),.LINE_BYTES(10)) stats(
  .clk(clk),.reset(reset),.vs(vs),.de(de),.irq(irq),.vc(vc),.dt(dt),.wc(wc),.ppc(ppc),
  .raw_pixels(32'h12345678),.values(values));
 task frame;
   input integer words;
   integer i;
   begin
     @(negedge clk);vs=1;
     for(i=0;i<words;i=i+1) begin
       @(negedge clk);de=1;
       @(negedge clk);de=0;
       repeat(2) @(negedge clk); // valid gaps are not row boundaries
     end
     @(negedge clk);vs=0;
     repeat(3) @(negedge clk);
   end
 endtask
 reg request=0;
 reg [63:0] data=64'h1122334455667788;
 wire [63:0] captured;
 wire done;
 snapshot_cdc #(.WIDTH(64)) bridge(.src_clk(src),.dst_clk(clk),.reset(reset),
  .request(request),.src_data(data),.dst_data(captured),.done(done));
 task req;
   begin @(negedge clk);request=1;@(negedge clk);request=0;end
 endtask
 reg send=0;
 wire tx,busy;
 video_uart #(.CYCLES(4)) uart(.clk(clk),.reset(reset),.start(send),
  .words(320'h0123456789abcdef_fedcba9876543210_00000000ffffffff_aabbccdd11223344_55aa55aa80000001),
  .tx(tx),.busy(busy));
 reg [7:0] received[0:95];
 reg [7:0] ch;
 integer count=0,j;
 always @(negedge tx) if(!reset) begin
   #60;
   for(j=0;j<8;j=j+1) begin ch[j]=tx;#40;end
   if(tx!==1) $fatal(1,"UART stop bit");
   received[count]=ch;count=count+1;
 end
 reg [8*96-1:0] expected="SCV1 01234567 89ABCDEF FEDCBA98 76543210 00000000 FFFFFFFF AABBCCDD 11223344 55AA55AA 80000001\015\012";
 integer k;
 initial begin
   #40;@(negedge clk);reset=0;
   frame(4);
   if(values[223:192]!=1 || values[191:160]!=0 || values[159:128]!=16)
     $fatal(1,"Good frame not counted");
   frame(3);wc=11;frame(4);wc=10;dt=6'h2a;frame(4);dt=6'h2b;
   if(values[223:192]!=1 || values[191:160]!=3) $fatal(1,"Invalid frames accepted");
   frame(4);
   if(values[223:192]!=2 || values[31:0]!=32'h48d159e0) $fatal(1,"Recovery/checksum failed");
   req;wait(done);#1;
   if(captured!==data) $fatal(1,"Torn snapshot");
   @(negedge src);run_src=0;data=64'h8877665544332211;req;
   repeat(50) @(negedge clk);
   if(done || captured===data) $fatal(1,"Stopped clock falsely acknowledged");
   req; // pending request must not toggle again
   repeat(20) @(negedge clk);run_src=1;wait(done);#1;
   if(captured!==data) $fatal(1,"Pending request lost after source resumes");
   @(negedge clk);send=1;@(negedge clk);send=0;
   wait(busy);wait(!busy);#100;
   if(count!=96) $fatal(1,"UART length=%0d",count);
   for(k=0;k<96;k=k+1) if(received[k]!==expected[8*(95-k)+:8])
     $fatal(1,"UART mismatch at %0d got=%h expected=%h",k,received[k],expected[8*(95-k)+:8]);
   $display("PASS frame accounting, invalid format/length, recovery, stable CDC, stopped source, UART bytes");
   $finish;
 end
 initial begin #1000000;$fatal(1,"Global timeout");end
endmodule
