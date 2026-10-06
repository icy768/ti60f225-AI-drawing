from pathlib import Path
ROOT=Path(__file__).resolve().parent
old=(ROOT/'ti60f225_oob.sdc').read_text()
base='\n'.join(l for l in old.splitlines() if not l.startswith(('set_input_delay','set_output_delay')) and 'jtag_inst1' not in l)
generated=(ROOT/'outflow/ti60f225_oob.pt.sdc').read_text()
delays=[l for l in generated.splitlines() if l.startswith(('set_input_delay','set_output_delay')) and 'jtag_inst1' not in l and not any('{'+p+'}' in l for p in ['ddr_addr[14]','ddr_addr[15]'])]
text=base+'\n'+'\n'.join(delays)+'\nset_false_path -from [get_ports {uart_rx}]\n'
(ROOT/'ti60f225_oob.sdc').write_text(text)
print('Updated',len(delays),'physical boundary constraints')
