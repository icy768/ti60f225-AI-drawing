// RISC-V (Sapphire) control and status registers on APB3 slave 0, base 0xF8100000.
// 0x0000-0x0FFF registers (see fw/src/stylecam_regs.h), 0x2000-0x3FFF OSD text cells (one char per word).
// One clock domain (core_clk); PREADY is always 1.
module sc_apb_regs #(parameter [31:0] VERSION=32'h5343_0A01,parameter integer I2C_TICK=1000)(
 input clk,rst,
 input [15:0] paddr,input psel,penable,pwrite,input [31:0] pwdata,output [31:0] prdata,output pready,output pslverr,
 output irq,
 output reg run,output reg step,output reg [1:0] style,output reg [1:0] view,output reg cam_enable,
 input ev_publish,ev_key3,ev_key2,ev_error,
 input [31:0] st_captured,st_processed,st_skipped,st_cap_errors,st_sensor_frames,st_video_errors,
 input [31:0] st_run_cycles,st_auto_cycles,st_auto_frames,st_hdmi_frames,st_hdmi_underflow,st_hdmi_errors,
 input [7:0] st_flags,input [10:0] st_sched,input [1:0] st_keys,
 input scl_in,sda_in,output scl_low,sda_low,
 output reg osd_we,output reg [10:0] osd_addr,output reg [7:0] osd_data,
 output reg cfg_we,output reg cfg_sel,output reg [4:0] cfg_lane,output reg [4:0] cfg_layer,output reg [11:0] cfg_addr,output reg [37:0] cfg_data);
 assign pready=1'b1;assign pslverr=1'b0;
 wire wr=psel&&penable&&pwrite;
 wire reg_sel=paddr[15:12]==4'h0;wire osd_sel=paddr[15:13]==3'b001;
 wire [5:0] ra=paddr[7:2];
 reg [3:0] pend,en;
 assign irq=|(pend&en);
 // camera I2C engine (16-bit register address, 8-bit data, 7-bit device 0x30)
 reg i2c_start,i2c_read,i2c_done;reg [15:0] i2c_addr;reg [7:0] i2c_wdata;
 wire i2c_busy,i2c_fin;wire [2:0] i2c_result;wire [7:0] i2c_rdata;
 i2c_reg16 #(.TICK_CYCLES(I2C_TICK),.TIMEOUT_TICKS(1000)) cam_i2c(.clk(clk),.reset(rst),.scl_in(scl_in),.sda_in(sda_in),
  .start(i2c_start),.read_op(i2c_read),.reg_addr(i2c_addr),.write_data(i2c_wdata),
  .scl_low(scl_low),.sda_low(sda_low),.busy(i2c_busy),.done(i2c_fin),.result(i2c_result),.read_data(i2c_rdata));
 always @(posedge clk)begin
  step<=0;osd_we<=0;cfg_we<=0;i2c_start<=0;
  if(rst)begin
   run<=0;style<=0;view<=0;cam_enable<=0;pend<=0;en<=0;i2c_read<=0;i2c_addr<=0;i2c_wdata<=0;i2c_done<=0;
   cfg_sel<=0;cfg_lane<=0;cfg_layer<=0;cfg_addr<=0;cfg_data<=0;osd_addr<=0;osd_data<=0;
  end else begin
   if(i2c_fin)i2c_done<=1;
   // events set pending bits; a W1C write clears them (an event in the same cycle wins)
   if(wr&&reg_sel&&ra==6'h03)pend<=pend&~pwdata[3:0];
   if(ev_publish)pend[0]<=1;if(ev_key3)pend[1]<=1;if(ev_key2)pend[2]<=1;if(ev_error)pend[3]<=1;
   if(wr&&osd_sel)begin osd_we<=1;osd_addr<=paddr[12:2];osd_data<=pwdata[7:0];end
   if(wr&&reg_sel)case(ra)
    6'h01:begin run<=pwdata[0];cam_enable<=pwdata[1];step<=pwdata[2];style<=pwdata[5:4];view<=pwdata[9:8];end
    6'h04:en<=pwdata[3:0];
    6'h05:if(!i2c_busy)begin i2c_addr<=pwdata[15:0];i2c_wdata<=pwdata[23:16];i2c_read<=pwdata[24];i2c_start<=1;i2c_done<=0;end
    // weight-blob record word 0: [31] sel (1 weights, 0 IN coefficients) [25:21] lane [20:16] layer [11:0] address
    6'h18:begin cfg_sel<=pwdata[31];cfg_lane<=pwdata[25:21];cfg_layer<=pwdata[20:16];cfg_addr<=pwdata[11:0];end
    6'h19:cfg_data[31:0]<=pwdata;
    6'h1a:begin cfg_data[37:32]<=pwdata[5:0];cfg_we<=1;end
    default:;
   endcase
  end
 end
 reg [31:0] q;
 always @*begin
  case(ra)
   6'h00:q=VERSION;
   6'h01:q={22'd0,view,2'd0,style,1'b0,1'b0,cam_enable,run};
   6'h02:q={3'd0,st_keys,st_sched,8'd0,st_flags};
   6'h03:q={28'd0,pend};
   6'h04:q={28'd0,en};
   6'h06:q={15'd0,i2c_done,i2c_rdata,4'd0,i2c_result,i2c_busy||i2c_start};
   6'h08:q=st_captured;   6'h09:q=st_processed;  6'h0a:q=st_skipped;    6'h0b:q=st_cap_errors;
   6'h0c:q=st_sensor_frames;6'h0d:q=st_video_errors;6'h0e:q=st_run_cycles;6'h0f:q=st_auto_cycles;
   6'h10:q=st_auto_frames;6'h11:q=st_hdmi_frames;6'h12:q=st_hdmi_underflow;6'h13:q=st_hdmi_errors;
   default:q=32'd0;
  endcase
 end
 assign prdata=reg_sel?q:32'd0;
endmodule
