`timescale 1ns/1ps
// Full-width changing spatial texture exposes row/lane alignment hidden by flat colors.
module spatial_tb;
 reg clk=0,rstn=0,vs=0,hs=0,de=0;
 reg [15:0] raw=0;
 always #5 clk=~clk;
 wire ovs,ohs,ode,valid;
 wire [47:0] rgb;
 debayer_top_2to1 dut(.in_pclk(clk),.in_rstn(rstn),.raw_vs_i(vs),.raw_hs_i(hs),
  .raw_de_i(de),.raw_valid_i(de),.raw_datax4_i(raw),
  .r_gain(16'd256),.g_gain(16'd256),.b_gain(16'd256),
  .rgb_vs_o(ovs),.rgb_hs_o(ohs),.rgb_de_o(ode),.rgb_valid_o(valid),.rgb_datax2_o(rgb));
 reg [7:0] scene[0:46079];
 integer x,y,ox=0,oy=0,fd;
 reg prev=0;
 always @(negedge clk) if(rstn) begin
   if(prev && !ode) begin oy=oy+1;ox=0;end
   if(ode && valid) begin
     $fwrite(fd,"%0d %0d %012h\n",oy,ox,rgb);
     ox=ox+1;
   end
   prev=ode;
 end
 initial begin
   $readmemh("validation/spatial_input.mem",scene);
   fd=$fopen("validation/spatial_output.txt","w");
   repeat(10) @(negedge clk);rstn=1;
   @(negedge clk);vs=1;repeat(4) @(negedge clk);vs=0;
   repeat(10) @(negedge clk);
   for(y=0;y<24;y=y+1) begin
     hs=1;repeat(22) @(negedge clk);hs=0;repeat(74) @(negedge clk);
     for(x=0;x<1920;x=x+2) begin
       de=1;raw={scene[y*1920+x+1],scene[y*1920+x]};@(negedge clk);
     end
     de=0;raw=0;repeat(44) @(negedge clk);
   end
   repeat(30) @(negedge clk);$fclose(fd);$finish;
 end
 initial begin #1000000;$fatal(1,"Timeout");end
endmodule
