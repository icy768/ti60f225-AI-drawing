from pathlib import Path
import hashlib,json,subprocess,sys
from sim_tool import executable
root=Path(__file__).resolve().parent
(root/'validation').mkdir(exist_ok=True)
logs=[]
def run(args):
    p=subprocess.run([executable(args[0]),*args[1:]],cwd=root,capture_output=True,text=True)
    logs.append(p.stdout+p.stderr)
    assert p.returncode==0,logs[-1]
    if p.stdout:print(p.stdout.strip())
run(['iverilog.exe','-g2012','-I','rtl/sc431hai','-s','stream_check_tb','-o','validation/setup.vvp',
     'sim/setup_tb.v','rtl/sc431hai/sc431hai_setup.v','rtl/sc431hai/i2c_reg16.v'])
for i in range(14):run(['vvp.exe','validation/setup.vvp',f'+CASE={i}'])
run(['iverilog.exe','-g2012','-s','diagnostics_tb','-o','validation/diagnostics.vvp',
     'sim/diagnostics_tb.v','rtl/sc431hai/video_monitor.v','rtl/sc431hai/video_uart.v'])
run(['vvp.exe','validation/diagnostics.vvp'])
for mode in range(2):
    run(['iverilog.exe','-g2012',f'-Pthumbnail_tb.ROI_MODE={mode}','-s','thumbnail_tb','-o','validation/thumbnail.vvp',
         'sim/thumbnail_tb.v','rtl/sc431hai/raw_thumbnail.v','rtl/sc431hai/video_uart.v'])
    run(['vvp.exe','validation/thumbnail.vvp'])
run(['iverilog.exe','-g2012','-s','black_level_tb','-o','validation/black_level.vvp',
     'sim/black_level_tb.v','rtl/sc431hai/raw_black_level.v'])
run(['vvp.exe','validation/black_level.vvp'])
run(['iverilog.exe','-g2012','-Pthumbnail_tb.ROI_MODE=1','-Pthumbnail_tb.X0=16','-Pthumbnail_tb.Y0=6',
     '-s','thumbnail_tb','-o','validation/thumbnail_offset.vvp',
     'sim/thumbnail_tb.v','rtl/sc431hai/raw_thumbnail.v','rtl/sc431hai/video_uart.v'])
run(['vvp.exe','validation/thumbnail_offset.vvp'])
run(['iverilog.exe','-g2012','-s','monitor_uart_tb','-o','validation/monitor_uart.vvp',
     'sim/monitor_uart_tb.v','rtl/sc431hai/video_monitor.v',
     'rtl/sc431hai/raw_thumbnail.v','rtl/sc431hai/video_uart.v'])
for i in range(3):run(['vvp.exe','validation/monitor_uart.vvp',f'+CASE={i}'])
run(['iverilog.exe','-g2012','-s','gamma_display_tb','-o','validation/gamma.vvp',
     'sim/gamma_display_tb.v','rtl/gamma_conrrection/gamma_correction.v'])
run(['vvp.exe','validation/gamma.vvp'])
for mode in range(2):
    run(['iverilog.exe','-g2012',f'-Pdebayer_tb.GAIN_CASE={mode}','-s','debayer_tb','-o','validation/debayer.vvp',
         'sim/debayer_tb.v','rtl/debayer/debayer_top_2to1.v','rtl/debayer/raw_to_rgb.v',
         'rtl/debayer/line_buffer.v','rtl/debayer/rgb_gain_v1.v','rtl/true_dual_port_ram.v','rtl/simple_dual_port_ram.v'])
    run(['vvp.exe','validation/debayer.vvp'])
for check in ['check_spatial.py','check_serializer.py']:
    result=subprocess.run([sys.executable,'-B',str(root/check)],cwd=root,capture_output=True,text=True)
    logs.append(result.stdout+result.stderr)
    assert result.returncode==0,logs[-1]
    print(result.stdout.strip())
(root/'validation/simulation.log').write_text('\n'.join(logs))
inputs={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
        for folder in ['rtl','sim'] for p in (root/folder).rglob('*') if p.is_file()}
(root/'validation/simulation_verified.json').write_text(json.dumps({'passed':True,'inputs':inputs},indent=2))
print('PASS all 27 simulation scenarios')
