module tb;
 reg clk=0;always #5 clk=~clk;reg rst=1;
 reg [15:0] paddr=0;reg psel=0,penable=0,pwrite=0;reg [31:0] pwdata=0;wire [31:0] prdata;wire pready,pslverr,irq;
 wire run,step,cam_enable,scl_low,sda_low,osd_we,cfg_we;wire [1:0] style,view;
 wire [10:0] osd_addr;wire [7:0] osd_data;wire cfg_sel;wire [4:0] cfg_lane,cfg_layer;wire [11:0] cfg_addr;wire [37:0] cfg_data;
 reg ev_pub=0,ev_k3=0,ev_k2=0,ev_err=0;
 // I2C slave model: device 0x30 ACKs everything, read data 0x5A
 wire scl=!scl_low,sda_m=!sda_low;
 sc_apb_regs #(.I2C_TICK(4)) dut(.clk(clk),.rst(rst),.paddr(paddr),.psel(psel),.penable(penable),.pwrite(pwrite),.pwdata(pwdata),
  .prdata(prdata),.pready(pready),.pslverr(pslverr),.irq(irq),.run(run),.step(step),.style(style),.view(view),.cam_enable(cam_enable),
  .ev_publish(ev_pub),.ev_key3(ev_k3),.ev_key2(ev_k2),.ev_error(ev_err),
  .st_captured(32'd11),.st_processed(32'd22),.st_skipped(32'd33),.st_cap_errors(32'd0),.st_sensor_frames(32'd44),.st_video_errors(32'd0),
  .st_run_cycles(32'd55),.st_auto_cycles(32'd66),.st_auto_frames(32'd13),.st_hdmi_frames(32'd77),.st_hdmi_underflow(32'd0),.st_hdmi_errors(32'd0),
  .st_flags(8'h3f),.st_sched(11'h5a5),.st_keys(2'b10),.scl_in(scl),.sda_in(sda_m&&sda_s),.scl_low(scl_low),.sda_low(sda_low),
  .osd_we(osd_we),.osd_addr(osd_addr),.osd_data(osd_data),.cfg_we(cfg_we),.cfg_sel(cfg_sel),.cfg_lane(cfg_lane),.cfg_layer(cfg_layer),.cfg_addr(cfg_addr),.cfg_data(cfg_data));
 // I2C slave: ACK every master byte, return 0x5A on the read data byte
 reg sda_s=1,rdphase=0;integer cnt=0,nbyte=0;
 always @(negedge sda_m)if(scl)begin if(nbyte>0||cnt>0)rdphase<=1;cnt<=-1;nbyte<=0;sda_s<=1;end
 always @(negedge scl)begin
  if(cnt+1==8)begin if(!(rdphase&&nbyte==1))sda_s<=0;else sda_s<=1;cnt<=cnt+1;end
  else if(cnt+1==9)begin cnt<=0;nbyte<=nbyte+1;sda_s<=(rdphase&&nbyte==0)?8'h5A>>7:1'b1;end
  else begin cnt<=cnt+1;if(rdphase&&nbyte==1)sda_s<=(8'h5A>>(7-(cnt+1)))&1;end
 end
 task apb_w(input [15:0] a,input [31:0] d);begin @(negedge clk);paddr=a;pwdata=d;pwrite=1;psel=1;@(negedge clk);penable=1;@(negedge clk);psel=0;penable=0;pwrite=0;@(negedge clk);end endtask
 task apb_r(input [15:0] a,output [31:0] d);begin @(negedge clk);paddr=a;pwrite=0;psel=1;@(negedge clk);penable=1;#1 d=prdata;@(negedge clk);psel=0;penable=0;end endtask
 reg [31:0] v;integer steps=0,osd_writes=0,cfg_writes=0;
 always @(posedge clk)begin if(step)steps<=steps+1;if(osd_we)osd_writes<=osd_writes+1;if(cfg_we)cfg_writes<=cfg_writes+1;end
 initial begin
  repeat(5)@(negedge clk);rst=0;
  apb_r(16'h0000,v);if(v!==32'h53430A01)$fatal(1,"ID %h",v);
  apb_w(16'h0004,32'h0000_0233);apb_r(16'h0004,v);
  if(!run||!cam_enable||style!=3||view!=2||v!==32'h0000_0233&~32'h4)$fatal(1,"CTRL %h",v);
  if(steps!=0)$fatal(1,"step without bit2");apb_w(16'h0004,32'h0000_0237);if(steps!=1)$fatal(1,"step pulse");
  apb_r(16'h0008,v);if(v!=={3'd0,2'b10,11'h5a5,8'd0,8'h3f})$fatal(1,"STATUS %h",v);
  apb_r(16'h0024,v);if(v!=22)$fatal(1,"processed");apb_r(16'h0044,v);if(v!=77)$fatal(1,"hdmi frames");
  // interrupts: enable publish+key2, raise publish and key3
  apb_w(16'h0010,32'h5);@(negedge clk);ev_pub=1;ev_k3=1;@(negedge clk);ev_pub=0;ev_k3=0;@(negedge clk);
  if(!irq)$fatal(1,"irq");apb_r(16'h000C,v);if(v!=3)$fatal(1,"pend %h",v);
  apb_w(16'h000C,32'h1);@(negedge clk);if(irq)$fatal(1,"irq after W1C (key3 masked)");apb_r(16'h000C,v);if(v!=2)$fatal(1,"pend after W1C %h",v);
  // event in the same cycle as W1C wins
  @(negedge clk);paddr=16'h000C;pwdata=32'h2;pwrite=1;psel=1;@(negedge clk);penable=1;ev_k3=1;@(negedge clk);psel=0;penable=0;pwrite=0;ev_k3=0;
  apb_r(16'h000C,v);if(v!=2)$fatal(1,"event lost during W1C %h",v);
  // OSD and coefficient writes
  apb_w(16'h2000+4*161,32'h41);@(negedge clk);if(osd_writes!=1)$fatal(1,"osd write");
  apb_w(16'h0060,{1'b1,5'd0,5'd3,5'd7,4'd0,12'h123});apb_w(16'h0064,32'hdeadbeef);if(cfg_writes)$fatal(1,"cfg commit early");
  apb_w(16'h0068,32'h2a);if(cfg_writes!=1||!cfg_sel||cfg_lane!=3||cfg_layer!=7||cfg_addr!=12'h123||cfg_data!=={6'h2a,32'hdeadbeef})$fatal(1,"cfg write");
  // I2C read of register 0x3107
  apb_w(16'h0014,{7'd0,1'b1,8'd0,16'h3107});
  repeat(4000)@(negedge clk);apb_r(16'h0018,v);
  if(v[0]||!v[16]||v[3:1]!=1)$fatal(1,"I2C status %h",v);
  $display("PASS apb regs: ID/CTRL/STATUS/counters, step pulse, IRQ mask + W1C + event priority, OSD and coefficient writes, I2C transaction (result %0d data %h)",v[3:1],v[15:8]);
  $finish;
 end
 initial begin #3000000;$fatal(1,"apb timeout");end
endmodule
