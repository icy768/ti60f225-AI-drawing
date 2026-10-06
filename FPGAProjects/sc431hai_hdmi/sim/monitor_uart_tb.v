`timescale 1ns/1ps
module monitor_uart_tb;
 reg clk=0,reset=1,vs=0,de=0,diag_valid=0;
 always #5 clk=~clk;
 wire tx;
 localparam [287:0] REGS={32'h003e0000,32'h003e01ba,32'h003e02d0,
   32'h00320e05,32'h00320fdc,32'h003e0803,32'h003e0940,32'h003e0600,32'h003e0780};
 video_monitor #(.REPORT_CYCLES(10000),.WAIT_CYCLES(20),.UART_CYCLES(4),
   .THUMB_REQUEST_CYCLES(40)) dut(
   .ref_clk(clk),.reset(reset),.pixel_clk(clk),.byte_clk(clk),.vs(vs),.de(de),
   .irq(1'b0),.ddr_ready(1'b1),.vc(2'd0),.dt(6'h2b),.wc(16'd2400),
   .setup_status(16'hba1f),.ppc(4'd4),.raw_pixels(32'h12345678),
   .diagnostic_words(REGS),.diagnostic_valid(diag_valid),.uart_tx(tx));
 reg [7:0] linebuf[0:95],ch;
 reg [31:0] tag;
 reg [287:0] decoded;
 integer n=0,k,i,j,pos,v,scv=0,raw=0,roi=0,sce=0,scenario=0;
 function integer hexval;
 input [7:0] c;
 begin
   if(c>="0" && c<="9") hexval=c-"0";
   else if(c>="A" && c<="F") hexval=c-"A"+10;
   else begin $fatal(1,"Non-hex UART byte: %h",c);hexval=0;end
 end
 endfunction
 always @(negedge tx) if(!reset) begin
   #60;
   for(k=0;k<8;k=k+1) begin ch[k]=tx;#40;end
   if(tx!==1) $fatal(1,"UART stop bit interrupted");
   linebuf[n]=ch;n=n+1;
   if(n==96) begin
     if(linebuf[94]!=13 || linebuf[95]!=10) $fatal(1,"Broken UART record boundary");
     for(i=4;i<94;i=i+9) if(linebuf[i]!=" ") $fatal(1,"Missing field separator");
     decoded=0;
     for(i=0;i<10;i=i+1) for(j=0;j<8;j=j+1) begin
       v=hexval(linebuf[5+i*9+j]);
       if(i>0) decoded={decoded[283:0],v[3:0]};
     end
     tag={linebuf[0],linebuf[1],linebuf[2],linebuf[3]};
     case(tag)
       "SCV1":scv=scv+1;
       "ROI1":begin
         if(decoded[287:256]!==roi) $fatal(1,"ROI block index");
         for(i=0;i<8;i=i+1)
           if(decoded[255-i*32 -: 32]!==32'h78563412) $fatal(1,"ROI adjacent pixel order");
         roi=roi+1;
       end
       "RAW1":begin
         if(decoded[287:256]!==raw || roi!=288) $fatal(1,"Overview index/priority");
         for(i=0;i<8;i=i+1)
           if(decoded[255-i*32 -: 32]!==32'h78123456) $fatal(1,"Overview stride/order");
         raw=raw+1;
       end
       "SCE1":begin
         sce=sce+1;
         if(decoded!==REGS) $fatal(1,"Register bytes corrupted in UART arbitration");
       end
       default:$fatal(1,"Corrupt UART magic %h",tag);
     endcase
     n=0;
   end
 end
 initial begin
   if(!$value$plusargs("CASE=%d",scenario)) scenario=0;
   repeat(10) @(negedge clk);reset=0;
   repeat(100) @(negedge clk);
   // Diagnostics arrive during status, ROI, or overview transfer.
   if(scenario==0) diag_valid=1;
   vs=1;@(negedge clk);
   for(pos=0;pos<518400;pos=pos+1) begin de=1;@(negedge clk);end
   de=0;vs=0;
   if(scenario==1) begin wait(roi==1);@(negedge clk);diag_valid=1;end
   if(scenario==2) begin wait(raw==1);@(negedge clk);diag_valid=1;end
   wait(raw==288 && roi==288 && sce==1);
   repeat(15000) @(negedge clk);
   if(scv<2 || sce!=1 || raw!=288 || roi!=288) $fatal(1,"Missing/repeated UART records");
   $display("PASS monitor UART arbitration case=%0d status=%0d overview=%0d roi=%0d registers=%0d",scenario,scv,raw,roi,sce);
   $finish;
 end
 initial begin #40000000;$fatal(1,"Monitor UART test timeout");end
endmodule
