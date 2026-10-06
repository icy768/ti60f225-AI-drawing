
/////////////////////////////////////////////////////////////////////////////
//
// Copyright (C) 2013-2021 Efinix Inc. All rights reserved.
//
// Description:
// Example top file for ti60f225 dev kit OOB design
//
// Language:  Verilog 2001
//Ti60f225_sc431hai2hdmi_v6：
//使用了最新版本的framebuffer_v3;
// ------------------------------------------------------------------------------

/////////////////////////////////////////////////////////////////////////////////
//`define SOFT_TAP 1
`include "ddr3_controller/ddr3_parameter.vh"
// `include "define.v"

module ti60f225_oob_top #(

	parameter                       RANK_RATIO         = 1,       // # of unique CS outputs per rank
	parameter                       ASYN_AXI_CLK       = `ASYN_AXI_CLK, 
	parameter                       RANKS              = `RANKS,
	parameter                       CK_WIDTH           = `CK_WIDTH,       // # of CK/CK# outputs to memory   
	parameter                       CKE_WIDTH          = `CKE_WIDTH,       // # of cke outputs
	parameter                       CS_WIDTH           = `CS_WIDTH,       // # of unique CS outputs
	parameter                       BANK_WIDTH         = `BANK_WIDTH,       // # of bank bits
	parameter                       ROW_WIDTH          = `ROW_WIDTH,       // DRAM address bus width
	parameter                       COL_WIDTH          = `COL_WIDTH,      // column address width
	parameter                       DM_WIDTH           = `DM_WIDTH,       // # of DM (data mask)
	parameter                       DQS_WIDTH          = `DQS_WIDTH,       // # of DQS (strobe)
	parameter                       DQ_WIDTH           = `DQ_WIDTH,      // # of DQ (data)
	parameter                       ODT_WIDTH          = `ODT_WIDTH,
	parameter                       DQ_CNT_WIDTH       = `DQ_CNT_WIDTH,       // = ceil(log2(DQ_WIDTH))
	parameter                       DQS_CNT_WIDTH      = `DQS_CNT_WIDTH,       // = ceil(log2(DQS_WIDTH))  
	parameter                       DRAM_WIDTH         = `DRAM_WIDTH,       // # of DQ per DQS   
	parameter                       DATA_WIDTH         = `DATA_WIDTH,
	parameter                       ADDR_WIDTH         = `ADDR_WIDTH,    
	parameter                       AXI_ID_WIDTH       = `AXI_ID_WIDTH,
	parameter                       AXI_ADDR_WIDTH     = `AXI_ADDR_WIDTH,
	parameter                       AXI_DATA_WIDTH     = `AXI_DATA_WIDTH
)
(


   //Clocks 
	input	wire	i_arstn,
 input wire style_key_n,
    output wire uart_tx,
 input wire uart_rx,
    input	wire	i_mipi_rx_pclk,
    input wire  vid_clk_dvi2,
    input wire hdmi_tx_slow_clk,
    input wire CLK_5M,
    input  wire CLK_25M,
	output  wire    pll_inst1_RSTN,
	input	wire	i_pll_locked,
	input 	wire  	pll_locked,
	output  wire    pll_inst4_RSTN,
	input   wire    pll_inst4_LOCKED,
	output  wire  	USER_PLL_RSTN,
    output 	wire 	DDR3_PLL_RSTN,
	input 	wire  	user_pll_locked,
    //CSI Interface
    input	 wire		io_cam_sda_IN,
    output wire   io_cam_sda_OUT,
    output wire		io_cam_sda_OE,

    output io_cam_scl_OUT,
    input io_cam_scl_IN,
    output io_cam_scl_OE,

    output	wire		o_cam_rst_p,
    
    input	wire		i_cam_ck_LP_P_IN,
    input	wire		i_cam_ck_LP_N_IN,
    output	wire		o_cam_ck_HS_TERM,
    output	wire		o_cam_ck_HS_ENA,
    input	wire		i_cam_ck_CLKOUT,
    
    input	wire	[7:0]			cam_d0_HS_IN,
    input	  wire		      cam_d0_LP_P_IN,
    input	  wire		      cam_d0_LP_N_IN,
    output	wire		      cam_d0_HS_TERM,
    output	wire		      cam_d0_HS_ENA,
    output	wire		      cam_d0_RST,
    output	wire		      cam_d0_FIFO_RD,
    input	  wire		      cam_d0_FIFO_EMPTY,
    
    input 	wire	[7:0]			cam_d1_HS_IN,
    input	  wire		        cam_d1_LP_P_IN,
    input	  wire		        cam_d1_LP_N_IN,
    output	wire		        cam_d1_HS_TERM,
    output	wire		        cam_d1_HS_ENA,
    output	wire		        cam_d1_RST,
    output	wire		        cam_d1_FIFO_RD,
    input	  wire		        cam_d1_FIFO_EMPTY,
    
    input 	wire	[7:0]			cam_d2_HS_IN,
    input	  wire		        cam_d2_LP_P_IN,
    input	  wire		        cam_d2_LP_N_IN,
    output	wire		        cam_d2_HS_TERM,
    output	wire		        cam_d2_HS_ENA,
    output	wire		        cam_d2_RST,
    output	wire		        cam_d2_FIFO_RD,
    input	  wire		        cam_d2_FIFO_EMPTY,  
   
    input 	wire	[7:0]			cam_d3_HS_IN,
    input	  wire		        cam_d3_LP_P_IN,
    input	  wire		        cam_d3_LP_N_IN,
    output	wire		        cam_d3_HS_TERM,
    output	wire		        cam_d3_HS_ENA,
    output	wire		        cam_d3_RST,
    output	wire		        cam_d3_FIFO_RD,
    input	  wire		        cam_d3_FIFO_EMPTY,

	
	input 					tx_cal_clk_90edge,
  	input 					rx_cal_clk,
  	input 					tx_cal_clk,
	input                              core_clk,     // CORE CLK @ 100MHz
	input                              sdram_clk,    // SDRAM CK @ 400MHz
	// PLL status flags  
	output [2:0]                       pll_shift,  
	output [4:0]                       pll_shift_sel,
	output                             pll_shift_ena,  
	// memory interface ports
	output                             ddr_ck_hi,
	output                             ddr_ck_lo,
	output                             ddr_reset_n,
	output [CKE_WIDTH-1:0]             ddr_cke,     
	output [ROW_WIDTH-1:0]             ddr_addr,
	output [BANK_WIDTH-1:0]            ddr_ba,
	output                             ddr_cas_n,
 
	output [CS_WIDTH*RANK_RATIO-1:0]   ddr_cs_n,
	output                             ddr_ras_n,
	output                             ddr_we_n,
	
	input  [DQS_WIDTH-1:0]             ddr_dqs_in_hi,
	input  [DQS_WIDTH-1:0]             ddr_dqs_in_lo,
	input  [DQ_WIDTH-1:0]              ddr_dq_in_hi,
	input  [DQ_WIDTH-1:0]              ddr_dq_in_lo,
	
	output [DQS_WIDTH-1:0]             ddr_dqs_oe,
	output [DQS_WIDTH-1:0]             ddr_dqs_oe_n,
	output [DQ_WIDTH-1:0]              ddr_dq_oe,  
	output [DQS_WIDTH-1:0]             ddr_dqs_out_hi,
	output [DQS_WIDTH-1:0]             ddr_dqs_out_lo,
	output [DQ_WIDTH-1:0]              ddr_dq_out_hi,
	output [DQ_WIDTH-1:0]              ddr_dq_out_lo,
	output [DM_WIDTH-1:0]              ddr_dm_hi,
	output [DM_WIDTH-1:0]              ddr_dm_lo,
	output [ODT_WIDTH-1:0]             ddr_odt,

       //LED
       output [7:0] led,

       // MIPI DSI
       input	wire	                     i_mipi_tx_pclk		,
       output	wire	                     mipi_dp_clk_LP_P_OUT		,
       output	wire	                     mipi_dp_clk_LP_N_OUT		,
       output	wire	[7:0] 	              mipi_dp_clk_HS_OUT		,
       output	wire	                     mipi_dp_clk_HS_OE		,
       output	wire	                     mipi_dp_data3_LP_P_OUT	,
       output	wire	                     mipi_dp_data2_LP_P_OUT	,
       output	wire	                     mipi_dp_data1_LP_P_OUT	,
       output	wire	                     mipi_dp_data0_LP_P_OUT	,
       output	wire	                     mipi_dp_data3_LP_N_OUT	,
       output	wire	                     mipi_dp_data2_LP_N_OUT	,
       output	wire	                     mipi_dp_data1_LP_N_OUT	,
       output	wire	                     mipi_dp_data0_LP_N_OUT	,
       output	wire	[7:0] 	              mipi_dp_data0_HS_OUT	       ,
       output	wire	[7:0] 	              mipi_dp_data1_HS_OUT	       ,
       output	wire	[7:0] 	              mipi_dp_data2_HS_OUT	       ,
       output	wire	[7:0] 	              mipi_dp_data3_HS_OUT	       ,
       output	wire	                     mipi_dp_data3_HS_OE		,
       output	wire	                     mipi_dp_data2_HS_OE		,
       output	wire	                     mipi_dp_data1_HS_OE		,
       output	wire	                     mipi_dp_data0_HS_OE		,

       output	wire	                     mipi_dp_clk_RST		,
       output	wire	                     mipi_dp_data0_RST		,
       output	wire	                     mipi_dp_data1_RST		,
       output	wire	                     mipi_dp_data2_RST		,
       output	wire	                     mipi_dp_data3_RST		,
       output	wire	                     mipi_dp_clk_LP_P_OE		,
       output	wire	                     mipi_dp_clk_LP_N_OE		,
       output	wire	                     mipi_dp_data3_LP_P_OE	,
       output	wire	                     mipi_dp_data3_LP_N_OE	,
       output	wire	                     mipi_dp_data2_LP_P_OE	,
       output	wire	                     mipi_dp_data2_LP_N_OE	,
       output	wire	                     mipi_dp_data1_LP_P_OE	,
       output	wire	                     mipi_dp_data1_LP_N_OE	,
       output	wire	                     mipi_dp_data0_LP_P_OE	,
       output	wire	                     mipi_dp_data0_LP_N_OE	,

       input  wire	                     mipi_dp_data0_LP_P_IN	,
       input  wire	                     mipi_dp_data0_LP_N_IN	,
       output	wire	                     LCD_RST_P			,
       output wire                        LCD_POWER			,

       // hdmi interface

    output tmds_tx_clk_TX_OE,
    output [9:0] tmds_tx_clk_TX_DATA,
    output tmds_tx_clk_TX_RST,
    output tmds_tx_data0_TX_OE,
    output [9:0] tmds_tx_data0_TX_DATA,
    output tmds_tx_data0_TX_RST,
    output tmds_tx_data1_TX_OE,
    output [9:0] tmds_tx_data1_TX_DATA,
    output tmds_tx_data1_TX_RST,
    output tmds_tx_data2_TX_OE,
    output [9:0] tmds_tx_data2_TX_DATA,
    output tmds_tx_data2_TX_RST


);

wire                              app_sr_active;
wire                              app_ref_ack;
wire                              app_zq_ack;
wire                              cal_done;

// Slave Interface Write Address Ports
wire [AXI_ID_WIDTH-1:0]           s_axi_awid;
wire [AXI_ADDR_WIDTH-1:0]         s_axi_awaddr;
wire [7:0]                        s_axi_awlen;
wire [2:0]                        s_axi_awsize;
wire [1:0]                        s_axi_awburst;
wire [0:0]                        s_axi_awlock;
wire [3:0]                        s_axi_awcache;
wire [2:0]                        s_axi_awprot;
wire                              s_axi_awvalid;
wire                              s_axi_awready;
// Slave Interface Write Data Ports
wire [AXI_DATA_WIDTH-1:0]         s_axi_wdata;
wire [(AXI_DATA_WIDTH/8)-1:0]     s_axi_wstrb;
wire                              s_axi_wlast;
wire                              s_axi_wvalid;
wire                              s_axi_wready;
// Slave Interface Write Response Ports
wire                              s_axi_bready;
wire [AXI_ID_WIDTH-1:0]           s_axi_bid;
wire [1:0]                        s_axi_bresp;
wire                              s_axi_bvalid;
// Slave Interface Read Address Ports
wire [AXI_ID_WIDTH-1:0]           s_axi_arid;
wire [AXI_ADDR_WIDTH-1:0]         s_axi_araddr;
wire [7:0]                        s_axi_arlen;
wire [2:0]                        s_axi_arsize;
wire [1:0]                        s_axi_arburst;
wire [0:0]                        s_axi_arlock;
wire [3:0]                        s_axi_arcache;
wire [2:0]                        s_axi_arprot;
wire                              s_axi_arvalid;
wire                              s_axi_arready;
// Slave Interface Read Data Ports
wire                              s_axi_rready;
wire [AXI_ID_WIDTH-1:0]           s_axi_rid;
wire [AXI_DATA_WIDTH-1:0]         s_axi_rdata;
wire [1:0]                        s_axi_rresp;
wire                              s_axi_rlast;
wire                              s_axi_rvalid;





assign cam_d0_RST=0;
assign cam_d1_RST=0;
assign cam_d2_RST=0;
assign cam_d3_RST=0;
assign mipi_dp_clk_LP_P_OUT=0;
assign mipi_dp_clk_LP_N_OUT=0;
assign mipi_dp_clk_HS_OUT=0;
assign mipi_dp_clk_HS_OE=0;
assign mipi_dp_data3_LP_P_OUT=0;
assign mipi_dp_data2_LP_P_OUT=0;
assign mipi_dp_data1_LP_P_OUT=0;
assign mipi_dp_data0_LP_P_OUT=0;
assign mipi_dp_data3_LP_N_OUT=0;
assign mipi_dp_data2_LP_N_OUT=0;
assign mipi_dp_data1_LP_N_OUT=0;
assign mipi_dp_data0_LP_N_OUT=0;
assign mipi_dp_data0_HS_OUT=0;
assign mipi_dp_data1_HS_OUT=0;
assign mipi_dp_data2_HS_OUT=0;
assign mipi_dp_data3_HS_OUT=0;
assign mipi_dp_data3_HS_OE=0;
assign mipi_dp_data2_HS_OE=0;
assign mipi_dp_data1_HS_OE=0;
assign mipi_dp_data0_HS_OE=0;
assign mipi_dp_clk_RST=0;
assign mipi_dp_data0_RST=0;
assign mipi_dp_data1_RST=0;
assign mipi_dp_data2_RST=0;
assign mipi_dp_data3_RST=0;
assign mipi_dp_clk_LP_P_OE=0;
assign mipi_dp_clk_LP_N_OE=0;
assign mipi_dp_data3_LP_P_OE=0;
assign mipi_dp_data3_LP_N_OE=0;
assign mipi_dp_data2_LP_P_OE=0;
assign mipi_dp_data2_LP_N_OE=0;
assign mipi_dp_data1_LP_P_OE=0;
assign mipi_dp_data1_LP_N_OE=0;
assign mipi_dp_data0_LP_P_OE=0;
assign mipi_dp_data0_LP_N_OE=0;
assign LCD_RST_P=0;
assign LCD_POWER=0;
assign pll_inst1_RSTN=i_arstn;
assign USER_PLL_RSTN=i_arstn;
assign DDR3_PLL_RSTN=i_arstn;
assign pll_inst4_RSTN=i_arstn;
wire w_arstn=i_arstn&i_pll_locked&pll_locked&user_pll_locked;
reg [15:0] power_count=0;
always @(posedge CLK_25M)if(!(&power_count))power_count<=power_count+1'b1;
wire global_reset=!(&power_count)||!w_arstn;
reg [2:0] rs_u=7,rs_a=7,rs_p=7;
always @(posedge CLK_25M or posedge global_reset)if(global_reset)rs_u<=7;else rs_u<={rs_u[1:0],1'b0};
always @(posedge core_clk or posedge global_reset)if(global_reset)rs_a<=7;else rs_a<={rs_a[1:0],1'b0};
always @(posedge hdmi_tx_slow_clk or posedge global_reset)if(global_reset)rs_p<=7;else rs_p<={rs_p[1:0],1'b0};

// Autonomous camera input ownership, network execution, and HDMI publication.
wire frame_ready,ready_bank,take_frame,release_frame,input_bank,cap_locked,cap_locked_bank;
wire engine_start,engine_idle,engine_done,engine_ok,engine_mode;
wire [1:0] engine_style,requested_style;wire [2:0] styles_ready;
wire output_bank,publish,publish_bank,output_complete,shown_valid,shown_bank;
wire [31:0] processed,video_errors,schedule_status;
wire [255:0] video_status;
wire [31:0] cap_awaddr,out_awaddr;wire [127:0] cap_wdata,out_wdata;
wire cap_awvalid,cap_awready,cap_wvalid,cap_wready,cap_bvalid,cap_bready;
wire out_awvalid,out_awready,out_wvalid,out_wready,out_bvalid,out_bready;
wire [31:0] captured,skipped,capture_errors,capture_overflow;
wire [39:0] camera_raw;wire camera_vs,camera_hs,camera_de;
wire [47:0] camera_rgb;wire camera_valid,camera_sof,camera_eof;
wire cam_enable,id_ok,config_ok,stream_set,setup_finished,diag_valid;
wire [2:0] setup_error;wire [7:0] setup_index;wire [287:0] diagnostics;
reg [287:0] diag_sync1,diag_sync2;
always @(posedge core_clk)begin diag_sync1<=diagnostics;diag_sync2<=diag_sync1;end
wire [31:0] camera_frames,camera_format_errors;
reg [31:0] cf1,cf2,ce1,ce2;reg [15:0] setup1,setup2;
always @(posedge core_clk)begin
 cf1<=camera_frames;cf2<=cf1;ce1<=camera_format_errors;ce2<=ce1;
 setup1<={setup_index,3'd0,setup_error,setup_finished,config_ok};setup2<=setup1;
end
sc_video_schedule schedule(.clk(core_clk),.rst(rs_a[2]),.key_n(style_key_n),
 .frame_ready(frame_ready),.ready_bank(ready_bank),.take_frame(take_frame),.release_frame(release_frame),.input_bank(input_bank),
 .engine_idle(engine_idle),.engine_done(engine_done),.engine_ok(engine_ok),.styles_ready(styles_ready),
 .engine_start(engine_start),.engine_style(engine_style),.engine_mode(engine_mode),
 .output_complete(output_complete),.shown_valid(shown_valid),.shown_bank(shown_bank),
 .output_bank(output_bank),.publish(publish),.publish_bank(publish_bank),
 .requested_style(requested_style),.processed(processed),.errors(video_errors),.state_status(schedule_status));
sc431hai_setup setup(.clk(CLK_25M),.reset(rs_u[2]),.scl_in(io_cam_scl_IN),.sda_in(io_cam_sda_IN),
 .scl_low(io_cam_scl_OE),.sda_low(io_cam_sda_OE),.cam_enable(cam_enable),.id_ok(id_ok),.config_ok(config_ok),
 .stream_set(stream_set),.finished(setup_finished),.error_code(setup_error),.command_index(setup_index),
 .diagnostic_words(diagnostics),.diagnostic_valid(diag_valid));
assign io_cam_sda_OUT=0;assign io_cam_scl_OUT=0;assign o_cam_rst_p=~cam_enable;
reg [2:0] camera_reset=7;
always @(posedge i_mipi_rx_pclk or posedge global_reset)if(global_reset)camera_reset<=7;else camera_reset<={camera_reset[1:0],1'b0};
sc_camera_rgb preprocess(.clk(i_mipi_rx_pclk),.rst(camera_reset[2]),.vs(camera_vs),.valid(camera_de&&camera_hs),.raw(camera_raw),
 .rgb(camera_rgb),.rgb_valid(camera_valid),.sof(camera_sof),.eof(camera_eof),.frames(camera_frames),.format_errors(camera_format_errors));
sc_capture capture(.cc(i_mipi_rx_pclk),.crst(camera_reset[2]),.rgb(camera_rgb),.cv(camera_valid),.sof(camera_sof),.eof(camera_eof),
 .ac(core_clk),.arst(rs_a[2]),.calibrated(cal_done),.take_frame(take_frame),.release_frame(release_frame),
 .frame_ready(frame_ready),.ready_bank(ready_bank),.locked(cap_locked),.locked_bank(cap_locked_bank),
 .completed(captured),.skipped(skipped),.errors(capture_errors),.overflow(capture_overflow),
 .awaddr(cap_awaddr),.awvalid(cap_awvalid),.awready(cap_awready),.wdata(cap_wdata),.wvalid(cap_wvalid),.wready(cap_wready),
 .bvalid(cap_bvalid),.bresp(s_axi_bresp),.bready(cap_bready));
sc_write_arbiter writes(.clk(core_clk),.rst(rs_a[2]),
 .a_addr(cap_awaddr),.a_av(cap_awvalid),.a_ar(cap_awready),.a_data(cap_wdata),.a_wv(cap_wvalid),.a_wr(cap_wready),.a_bv(cap_bvalid),.a_br(cap_bready),
 .b_addr(out_awaddr),.b_av(out_awvalid),.b_ar(out_awready),.b_data(out_wdata),.b_wv(out_wvalid),.b_wr(out_wready),.b_bv(out_bvalid),.b_br(out_bready),
 .awaddr(s_axi_awaddr),.awvalid(s_axi_awvalid),.awready(s_axi_awready),.wdata(s_axi_wdata),.wvalid(s_axi_wvalid),.wready(s_axi_wready),.bvalid(s_axi_bvalid),.bready(s_axi_bready));
assign video_status={cf2,video_errors,setup2,8'd0,3'd0,requested_style,styles_ready,capture_overflow,capture_errors,skipped,processed,captured};
csi_rx_controller inst_efx_csi2_rx
		(
              .reset_n			(i_arstn),
              .clk				(core_clk),
              .reset_byte_HS_n	(i_arstn),
              .clk_byte_HS		  (i_cam_ck_CLKOUT),
              .reset_pixel_n		(~camera_reset[2]),
              .clk_pixel			  (i_mipi_rx_pclk),
              
              .Rx_LP_CLK_P		  (i_cam_ck_LP_P_IN),
              .Rx_LP_CLK_N		  (i_cam_ck_LP_N_IN),
              .Rx_HS_enable_C		(o_cam_ck_HS_ENA),
              .LVDS_termen_C		(o_cam_ck_HS_TERM),
              
              .Rx_LP_D_P			({cam_d3_LP_P_IN, cam_d2_LP_P_IN, cam_d1_LP_P_IN, cam_d0_LP_P_IN}),//(r_mipi_rx_data_LP_P_IN_2P),
              .Rx_LP_D_N			({cam_d3_LP_N_IN, cam_d2_LP_N_IN, cam_d1_LP_N_IN, cam_d0_LP_N_IN}),//(r_mipi_rx_data_LP_N_IN_2P),
              .Rx_HS_D_0			(cam_d0_HS_IN),//(r_mipi_rx_data_HS_IN_2P[0*8+:8]),
              .Rx_HS_D_1			(cam_d1_HS_IN),//(r_mipi_rx_data_HS_IN_2P[1*8+:8]),
              .Rx_HS_D_2			(cam_d2_HS_IN),
              .Rx_HS_D_3			(cam_d3_HS_IN),
              .Rx_HS_D_4			(),
              .Rx_HS_D_5			(),
              .Rx_HS_D_6			(),
              .Rx_HS_D_7			(),
              .Rx_HS_enable_D		({cam_d3_HS_ENA    ,cam_d2_HS_ENA    ,cam_d1_HS_ENA    ,cam_d0_HS_ENA    }),//( w_cam_d_HS_ENA),
              .LVDS_termen_D		({cam_d3_HS_TERM   ,cam_d2_HS_TERM   ,cam_d1_HS_TERM   ,cam_d0_HS_TERM   }),
              .fifo_rd_enable		({cam_d3_FIFO_RD   ,cam_d2_FIFO_RD   ,cam_d1_FIFO_RD   ,cam_d0_FIFO_RD   }),
              .fifo_rd_empty		({cam_d3_FIFO_EMPTY,cam_d2_FIFO_EMPTY,cam_d1_FIFO_EMPTY,cam_d0_FIFO_EMPTY}),
              .DLY_enable_D		       (),
              .DLY_inc_D			(),
              .u_dly_enable_D		(),
              .u_dly_inc_D		       (),
              
              .axi_clk			(1'b0),
              .axi_reset_n		       (1'b0),
              .axi_awaddr			(6'b0),
              .axi_awvalid		       (1'b0),
              .axi_awready		       (),
              .axi_wdata			(32'b0),
              .axi_wvalid			(1'b0),
              .axi_wready			(),
              
              .axi_bvalid			(),
              .axi_bready			(1'b0),
              .axi_araddr			(6'b0),
              .axi_arvalid		       (1'b0),
              .axi_arready		       (),
              .axi_rdata			(),
              .axi_rvalid			(),
              .axi_rready			(1'b1),
              
              .hsync_vc0			(camera_hs),
              .hsync_vc1			(),
              .hsync_vc2			(),
              .hsync_vc3			(),
              .vsync_vc0			(camera_vs),
              .vsync_vc1			(),
              .vsync_vc2			(),
              .vsync_vc3			(),
              .vc (),
              .word_count (),
              .shortpkt_data_field        (),
              .datatype (),
              .pixel_per_clk (),
              .pixel_data			(camera_raw),
              .pixel_data_valid	       (camera_de),
              .irq ()//,
              // .mipi_debug_out(mipi_debug_out)
		);
wire [23:0] sink_data;wire sink_valid,sink_ready,new_frame,original_frame;
wire [23:0] replay_data;wire replay_valid,replay_ready,replay_start,replay_busy;
wire [31:0] replay_errors;
wire [31:0] da,ra;wire dav,dardy,drv,drr,rav,rardy,rrv,rrr;
sc_replay replay(.uc(core_clk),.urst(rs_a[2]),.ac(core_clk),.arst(rs_a[2]),.start(replay_start),.bank(input_bank),
 .pixel(replay_data),.valid(replay_valid),.ready(replay_ready),.busy(replay_busy),.errors(replay_errors),
 .araddr(ra),.arvalid(rav),.arready(rardy),.rdata(s_axi_rdata),.rvalid(rrv),.rlast(s_axi_rlast),.rresp(s_axi_rresp),.rready(rrr));
sc_read_arbiter #(.DISPLAY_PRIORITY(1)) reads(.clk(core_clk),.rst(rs_a[2]),
 .a_addr(da),.a_valid(dav),.a_ready(dardy),.a_rvalid(drv),.a_rready(drr),
 .b_addr(ra),.b_valid(rav),.b_ready(rardy),.b_rvalid(rrv),.b_rready(rrr),
 .araddr(s_axi_araddr),.arvalid(s_axi_arvalid),.arready(s_axi_arready),
 .rvalid(s_axi_rvalid),.rlast(s_axi_rlast),.rready(s_axi_rready));
wire [1:0] display_mode;wire [1:0] current_style;wire [255:0] display_status;
StyleCam_uart #(.IN_TRACE(0),.DIV(108),.KEY_CYCLES(1000000),.CLOCK_HZ(100000000)) control(.clk_25m(core_clk),.uart_rx(uart_rx),.uart_tx(uart_tx),.system_reset(rs_a[2]),.style_key_n(1'b1),.current_style(current_style),
 .sink_ready(sink_ready),.sink_data(sink_data),.sink_valid(sink_valid),.new_frame(new_frame),
 .original_frame(original_frame),.display_mode(display_mode),.display_status(display_status),
 .replay_data(replay_data),.replay_valid(replay_valid),.replay_ready(replay_ready),
 .replay_start(replay_start),.replay_busy(replay_busy),.replay_errors(replay_errors),
 .video_enabled(1'b1),.video_start(engine_start),.video_style(engine_style),.video_mode(engine_mode),
 .video_idle(engine_idle),.video_done(engine_done),.video_ok(engine_ok),.video_styles_ready(styles_ready),
 .video_status(video_status),.sensor_diagnostics(diag_sync2));
wire hs,vs,de;wire [7:0] red,green,blue;
sc_display display(.uc(core_clk),.urst(rs_a[2]),.ac(core_clk),.arst(rs_a[2]),
 .pc(hdmi_tx_slow_clk),.prst(rs_p[2]),.calibrated(cal_done),
 .pixel(sink_data),.pv(sink_valid),.pready(sink_ready),.new_frame(new_frame),.original_frame(original_frame),
 .mode(2'd2),.status(display_status),.write_bank(output_bank),
 .publish(publish),.publish_bank(publish_bank),.output_complete(output_complete),.shown_valid(shown_valid),.shown_bank(shown_bank),
 .awaddr(out_awaddr),.awvalid(out_awvalid),.awready(out_awready),
 .wdata(out_wdata),.wvalid(out_wvalid),.wready(out_wready),.bvalid(out_bvalid),.bresp(s_axi_bresp),.bready(out_bready),
 .araddr(da),.arvalid(dav),.arready(dardy),
 .rdata(s_axi_rdata),.rvalid(drv),.rlast(s_axi_rlast),.rresp(s_axi_rresp),.rready(drr),
 .hs(hs),.vs(vs),.de(de),.red(red),.green(green),.blue(blue));
assign s_axi_awid=0;assign s_axi_awlen=0;assign s_axi_awsize=4;assign s_axi_awburst=1;
assign s_axi_awlock=0;assign s_axi_awcache=0;assign s_axi_awprot=0;
assign s_axi_wstrb=16'hffff;assign s_axi_wlast=1;
assign s_axi_arid=0;assign s_axi_arlen=15;assign s_axi_arsize=4;assign s_axi_arburst=1;
assign s_axi_arlock=0;assign s_axi_arcache=0;assign s_axi_arprot=0;
reg [25:0] heartbeat=0;always @(posedge CLK_25M)heartbeat<=heartbeat+1'b1;
assign led={setup_finished,|setup_error,config_ok,stream_set,requested_style,cal_done,heartbeat[24]};
wire [9:0] td0,td1,td2,tck;
dvi_encoder video(.pixelclk(hdmi_tx_slow_clk),.rst_p(rs_p[2]),.i_bdata(blue),.i_gdata(green),.i_rdata(red),
 .i_de(de),.i_hs(hs),.i_vs(vs),.video_format(2'd0),.video_VIC(8'd16),
 .audio_L(24'd0),.audio_R(24'd0),.audio_valid(1'b0),.audio_N(20'd6144),.audio_CTS(20'd148500),
 .audio_sample_frequency(3'd0),.audio_word_length(4'b1011),.tmds_data0(td0),.tmds_data1(td1),.tmds_data2(td2),.tmds_clk(tck));
assign tmds_tx_clk_TX_DATA=~tck;assign tmds_tx_data0_TX_DATA=~td0;assign tmds_tx_data1_TX_DATA=~td1;assign tmds_tx_data2_TX_DATA=~td2;
assign tmds_tx_clk_TX_OE=1;assign tmds_tx_data0_TX_OE=1;assign tmds_tx_data1_TX_OE=1;assign tmds_tx_data2_TX_OE=1;
assign tmds_tx_clk_TX_RST=0;assign tmds_tx_data0_TX_RST=0;assign tmds_tx_data1_TX_RST=0;assign tmds_tx_data2_TX_RST=0;

ddr3_top                 u_ddr3_top
(

.axi_clk                (core_clk            ),
.core_clk               (core_clk            ),
.sdram_clk              (sdram_clk           ),  
.rx_cal_clk             (rx_cal_clk          ),
.tx_cal_clk             (tx_cal_clk          ),
.tx_cal_clk_90edge      (tx_cal_clk_90edge   ),
.rstn                   (w_arstn             ),      
.pll_shift              (pll_shift           ),
.pll_shift_sel          (pll_shift_sel       ),
.pll_shift_ena          (pll_shift_ena       ),       
///////////////DDR BUS
.ddr_ck_hi              (ddr_ck_hi           ),
.ddr_ck_lo              (ddr_ck_lo           ),
.ddr_cke                (ddr_cke             ),    
.ddr_reset_n            (ddr_reset_n         ),
.ddr_cs_n               (ddr_cs_n            ),
.ddr_ras_n              (ddr_ras_n           ),
.ddr_cas_n              (ddr_cas_n           ),
.ddr_we_n               (ddr_we_n            ),     
.ddr_addr               (ddr_addr            ),
.ddr_ba                 (ddr_ba              ),

.ddr_dqs_oe             (ddr_dqs_oe          ),
.ddr_dqs_oe_n           (ddr_dqs_oe_n        ),
.ddr_dq_oe              (ddr_dq_oe           ),
.ddr_dqs_in_hi          (ddr_dqs_in_hi       ),
.ddr_dqs_in_lo          (ddr_dqs_in_lo       ),
.ddr_dq_in_hi           (ddr_dq_in_hi        ),
.ddr_dq_in_lo           (ddr_dq_in_lo        ),

.ddr_dqs_out_hi         (ddr_dqs_out_hi      ),
.ddr_dqs_out_lo         (ddr_dqs_out_lo      ),
.ddr_dq_out_hi          (ddr_dq_out_hi       ),
.ddr_dq_out_lo          (ddr_dq_out_lo       ),

.ddr_dm_hi              (ddr_dm_hi           ),
.ddr_dm_lo              (ddr_dm_lo           ),
.ddr_odt                (ddr_odt             ),

// Application interface ports
.app_sr_req                     (1'b0),
.app_ref_req                    (1'b0),
.app_zq_req                     (1'b0),
.app_sr_active                  (app_sr_active),
.app_ref_ack                    (app_ref_ack),
.app_zq_ack                     (app_zq_ack),

// Slave Interface Write Address Ports
.s_axi_awid                     (s_axi_awid        ),
.s_axi_awaddr                   (s_axi_awaddr      ),
.s_axi_awlen                    (s_axi_awlen       ),
.s_axi_awsize                   (s_axi_awsize      ),
.s_axi_awburst                  (s_axi_awburst     ),
.s_axi_awlock                   (s_axi_awlock      ),
.s_axi_awcache                  (s_axi_awcache     ),
.s_axi_awprot                   (s_axi_awprot      ),
.s_axi_awqos                    (4'h0              ),
.s_axi_awvalid                  (s_axi_awvalid     ),
.s_axi_awready                  (s_axi_awready     ),
// Slave Interface Write Data Ports
.s_axi_wdata                    (s_axi_wdata       ),
.s_axi_wstrb                    (s_axi_wstrb       ),
.s_axi_wlast                    (s_axi_wlast       ),
.s_axi_wvalid                   (s_axi_wvalid      ),
.s_axi_wready                   (s_axi_wready      ),
// Slave Interface Write Response Ports
.s_axi_bid                      (s_axi_bid         ),
.s_axi_bresp                    (s_axi_bresp       ),
.s_axi_bvalid                   (s_axi_bvalid      ),
.s_axi_bready                   (s_axi_bready      ),
// Slave Interface Read Address Ports
.s_axi_arid                     (s_axi_arid        ),
.s_axi_araddr                   (s_axi_araddr      ),
.s_axi_arlen                    (s_axi_arlen       ),
.s_axi_arsize                   (s_axi_arsize      ),
.s_axi_arburst                  (s_axi_arburst     ),
.s_axi_arlock                   (s_axi_arlock      ),
.s_axi_arcache                  (s_axi_arcache     ),
.s_axi_arprot                   (s_axi_arprot      ),
.s_axi_arqos                    (4'h0              ),
.s_axi_arvalid                  (s_axi_arvalid     ),
.s_axi_arready                  (s_axi_arready     ),
// Slave Interface Read Data Ports
.s_axi_rid                      (s_axi_rid         ),
.s_axi_rdata                    (s_axi_rdata       ),
.s_axi_rresp                    (s_axi_rresp       ),
.s_axi_rlast                    (s_axi_rlast       ),
.s_axi_rvalid                   (s_axi_rvalid      ),
.s_axi_rready                   (s_axi_rready      ),
//DEBUG       
.wrlvl_dq_check() ,
.rd_level_dqs_check() ,
.init_cur_state() ,
.idelay_ld() ,
.mpr_rdlvl_dly() ,
.cal_done                       (cal_done          ) 
);


endmodule
