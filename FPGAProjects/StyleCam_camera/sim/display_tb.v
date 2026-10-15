module tb;
 reg clk=0,pc=0;always #5 clk=~clk;always #7 pc=~pc;reg rst=1;
 reg [23:0] pixel=0;reg pv=0,nf=0,pub=0;reg [1:0] bank=0,pb=0;wire pready,complete,shown_valid;wire [1:0] shown_bank;
 wire [255:0] status;wire [31:0] awaddr,araddr;wire av,wv,br,arv,rr;wire [127:0] wd;
 reg awready=0,wready=0,bvalid=0;reg [1:0] bresp=0;reg bad=0;reg [1:0] ws=0;
 reg [31:0] write_addr;reg [127:0] memory[0:191];integer wait_b=0,cycle=0,writes=0;
 function integer bank_index(input [31:0] a);begin
  case(a[31:20])12'h004:bank_index=0;12'h006:bank_index=1;12'h00a:bank_index=2;default:bank_index=-1;endcase
 end endfunction
 reg reading=0,stall=0;reg [31:0] read_addr;reg [3:0] beat=0;
 wire rvalid=reading&&!stall;wire [127:0] rd=memory[bank_index(read_addr)*64+read_addr[19:4]+beat];
 sc_display #(.IW(64),.IH(4)) dut(.uc(clk),.urst(rst),.ac(clk),.arst(rst),.pc(pc),.prst(rst),.calibrated(1'b1),
 .pixel(pixel),.pv(pv),.pready(pready),.new_frame(nf),.original_frame(1'b0),.mode(2'd1),.status(status),
 .write_bank(bank),.publish(pub),.publish_bank(pb),.publish_orig(2'd0),.osd_we(1'b0),.osd_addr(11'd0),.osd_data(8'd0),.output_complete(complete),.shown_valid(shown_valid),.shown_bank(shown_bank),
 .awaddr(awaddr),.awvalid(av),.awready(awready),.wdata(wd),.wvalid(wv),.wready(wready),.bvalid(bvalid),.bresp(bresp),.bready(br),
 .araddr(araddr),.arvalid(arv),.arready(!reading),.rdata(rd),.rvalid(rvalid),.rlast(beat==15),.rresp(2'd0),.rready(rr),.hs(),.vs(),.de(),.red(),.green(),.blue());
 always @(posedge clk)begin
  if(rst)begin ws<=0;awready<=0;wready<=0;bvalid<=0;reading<=0;end
  else begin
   cycle<=cycle+1;awready<=ws==0&&cycle%3!=0;wready<=ws==1&&cycle%4!=0;
   if(av&&awready)begin
    if(bank_index(awaddr)<0)$fatal(1,"Output bank address");
    if(shown_valid&&bank_index(awaddr)==shown_bank)$fatal(1,"Overwrote HDMI front bank");
    ws<=1;write_addr<=awaddr;awready<=0;
   end
   if(wv&&wready)begin memory[bank_index(write_addr)*64+write_addr[19:4]]<=wd;writes<=writes+1;ws<=2;wready<=0;wait_b<=cycle%5+1;bresp<=bad?2:0;end
   if(ws==2&&!bvalid)begin if(wait_b==0)bvalid<=1;else wait_b<=wait_b-1;end
   if(bvalid&&br)begin bvalid<=0;ws<=0;end
   if(arv&&!reading)begin if(bank_index(araddr)<0)$fatal(1,"Read bank address");reading<=1;read_addr<=araddr;beat<=0;end
   if(rvalid&&rr)begin beat<=beat+1'b1;if(beat==15)reading<=0;end
  end
 end
 task frame(input integer base);
  integer i,k,target_writes;begin
   target_writes=writes+64;
   @(negedge clk);nf=1;@(negedge clk);nf=0;
   for(i=0;i<256;i=i+1)begin
    pixel=24'(base+i);pv=1;@(negedge clk);while(!pready)@(negedge clk);
   end
   pv=0;wait(writes==target_writes);repeat(12)@(negedge clk);
   if(!complete)$fatal(1,"Complete output not ready");
   for(i=0;i<64;i=i+1)for(k=0;k<4;k=k+1)
    if(memory[bank*64+i][k*32+:32]!==32'(base+i*4+k))$fatal(1,"Output packing");
  end
 endtask
 task publish(input [1:0] b);begin @(negedge clk);pb=b;pub=1;@(negedge clk);pub=0;repeat(5)@(negedge pc);end endtask
 task blank;begin
  @(negedge pc);force dut.x=0;force dut.y=1080;@(negedge pc);release dut.x;release dut.y;
 end endtask
 integer before_w,i;
 initial begin
  repeat(8)@(negedge clk);rst=0;frame(1000);
  if(shown_valid)$fatal(1,"Unpublished frame displayed");publish(0);blank;
  wait(shown_valid);wait(reading&&beat==5);@(negedge clk);stall=1;
  bank=1;frame(2000);publish(1);
  repeat(10)@(negedge clk);if(shown_bank!=0)$fatal(1,"Changed before vertical blank");
  blank;wait(dut.restart);repeat(20)@(negedge clk);if(shown_bank!=0)$fatal(1,"Released old bank with outstanding R transaction");
  stall=0;wait(shown_bank==1);
  bank=2;frame(3000);publish(2);blank;wait(shown_bank==2);
  wait(reading);if(bank_index(read_addr)!=2)$fatal(1,"Third bank not scanned");
  bank=0;bad=1;before_w=writes;
  @(negedge clk);nf=1;@(negedge clk);nf=0;
  for(i=0;i<256;i=i+1)begin pixel=24'(3000+i);pv=1;@(negedge clk);while(!pready)@(negedge clk);end
  pv=0;wait(writes==before_w+64);repeat(15)@(negedge clk);
  if(complete||dut.valid_banks[0])$fatal(1,"AXI-error output published as valid");
  rst=1;repeat(6)@(negedge clk);if(shown_valid)$fatal(1,"Display reset");
  $display("PASS output triple buffer: 768 packed pixels, all three DDR banks and 2-bit CDC publication, vertical-blank swap, delayed read retirement, front-bank protection, AXI error gate, reset");$finish;
 end
 initial begin #1000000;$fatal(1,"Display timeout");end
endmodule
