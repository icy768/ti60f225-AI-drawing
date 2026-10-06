"""Test the exact current top-level serializer without a second RTL implementation."""
from pathlib import Path
import subprocess,hashlib,json
from sim_tool import executable
root=Path(__file__).resolve().parent
top=(root/'rtl/ti60f225_oob_top.v').read_text(encoding='utf-8')
block=top.split("reg rgb_vs_r = 'd0;")[1].split('//==============================================================================')[0]
block="reg rgb_vs_r = 'd0;"+block
header='''module serializer_under_test(input hdmi_tx_slow_clk,rgb_vs,rgb_hs,rgb_de,
input [47:0] rgb_datax2,output reg hdmi_tx_vs,hdmi_tx_hs,hdmi_tx_de,output [23:0] rgb);
wire pos_vs;
'''
for name in ['hdmi_tx_vs','hdmi_tx_hs','hdmi_tx_de']:
    block=block.replace('reg '+name+';','')
source=header+block+'\nassign rgb={hdmi_tx_bdata,hdmi_tx_gdata,hdmi_tx_rdata};\nendmodule\n'
(root/'validation/serializer_under_test.v').write_text(source)
logs=[]
for exe,args in [('iverilog.exe',['-g2012','-s','serializer_tb','-o','validation/serializer.vvp',
                                'sim/serializer_tb.v','validation/serializer_under_test.v']),
                 ('vvp.exe',['validation/serializer.vvp'])]:
    result=subprocess.run([executable(exe),*args],cwd=root,capture_output=True,text=True)
    logs.append(result.stdout+result.stderr)
    (root/'validation/serializer_simulation.log').write_text('\n'.join(logs))
    assert result.returncode==0,logs[-1]
print(logs[-1].strip())
(root/'validation/serializer_result.json').write_text(json.dumps({
 'passed':True,'top_sha256':hashlib.sha256((root/'rtl/ti60f225_oob_top.v').read_bytes()).hexdigest(),
 'tested_pixels':23040,'method':'Exact source block extracted from top-level; related clocks with coincident rising edges',
 'limits':'Digital pixel order/sync only; not TMDS electrical quality or monitor scaling'},indent=2))
