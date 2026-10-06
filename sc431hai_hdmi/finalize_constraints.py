"""Use this project's generated four-lane I3 boundary delays, not old coordinates."""
from pathlib import Path
root=Path(__file__).resolve().parent
generated=(root/'outflow/ti60f225_oob.pt.sdc').read_text()
inactive=('jtag_inst1_DRCK','ddr_addr[14]','ddr_addr[15]')
delays=[l for l in generated.splitlines() if l.startswith(('set_input_delay','set_output_delay'))
        and not any('{'+p+'}' in l for p in inactive)]
for lane in range(4):assert any(f'cam_d{lane}_HS_IN' in l for l in delays)
clocks={'tx_cal_clk_90edge':2.5,'sdram_clk':2.5,'rx_cal_clk':2.5,'tx_cal_clk':2.5,
        'core_clk':10,'i_mipi_rx_pclk':20,'vid_clk_dvi2':13.468,
        'hdmi_tx_slow_clk':6.734,'CLK_25M':40,'i_cam_ck_CLKOUT':14.285714,'jtag_inst1_TCK':100}
text='# SC431HAI v3.5 receiver: nominal 70 MHz byte clock; measure on hardware.\n'
text+='\n'.join(f'create_clock -period {v} -name {k} [get_ports {{{k}}}]' for k,v in clocks.items())+'\n'
text+='''# Board reset/lock and synchronized asynchronous control inputs.
set_false_path -from [get_ports {i_arstn i_pll_locked pll_locked user_pll_locked io_cam_scl_IN io_cam_sda_IN i_cam_ck_LP_P_IN i_cam_ck_LP_N_IN cam_d0_LP_P_IN cam_d0_LP_N_IN cam_d1_LP_P_IN cam_d1_LP_N_IN cam_d2_LP_P_IN cam_d2_LP_N_IN cam_d3_LP_P_IN cam_d3_LP_N_IN}]
set_false_path -to [get_ports {led[*] uart_tx io_cam_scl_OUT io_cam_scl_OE io_cam_sda_OUT io_cam_sda_OE o_cam_rst_p pll_inst1_RSTN USER_PLL_RSTN DDR3_PLL_RSTN}]
# Inherited DDR/FIFO domain exceptions; keep related 74.25/148.5 MHz timing.
'''
groups=['core_clk','tx_cal_clk','vid_clk_dvi2 hdmi_tx_slow_clk','i_mipi_rx_pclk','sdram_clk','rx_cal_clk']
pairs={(a,b) for a in groups for b in groups if a!=b}
for independent in ['CLK_25M','i_cam_ck_CLKOUT','jtag_inst1_TCK']:
    for other in clocks:
        if other!=independent:pairs.update(((independent,other),(other,independent)))
text+='\n'.join(f'set_false_path -from [get_clocks {{{a}}}] -to [get_clocks {{{b}}}]' for a,b in sorted(pairs))+'\n'
text+='\n'.join(delays)+'\n'
(root/'ti60f225_oob.sdc').write_text(text)
print(f'{len(delays)} generated boundary delays; four J4 data lanes; I3')
