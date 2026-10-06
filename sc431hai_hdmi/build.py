"""Run one offline Efinity flow, retaining uniquely named logs."""
from pathlib import Path
import datetime
import os
import subprocess
import sys
import xml.etree.ElementTree as ET

root=Path(__file__).resolve().parent
name='ti60f225_oob'
flow=sys.argv[1]
assert flow in ['interface','map','pnr','pgm']
env=os.environ.copy()
env.update(PROCESSOR_ARCHITECTURE='AMD64',PYTHONDONTWRITEBYTECODE='1')
if flow!='pgm':
    env.pop('EFINITY_HOME',None)  # Vendor launcher supplies its Python/SDK environment.
    cmd=['C:/Efinity/2026.1/bin/efx_run.bat',name+'.xml','--flow',flow]
else:
    env['EFINITY_HOME']='C:/Efinity/2026.1'
    # Relative paths avoid the vendor bitstream generator's non-ASCII path bug.
    allowed=['mode','width','enable_roms','spi_low_power_mode','io_weak_pullup',
        'oscillator_clock_divider','bitstream_compression','enable_external_master_clock',
        'active_capture_clk_edge','jtag_usercode','release_tri_then_reset']
    params={x.get('name'):x.get('value') for x in ET.parse(root/(name+'.xml')).findall(
        './/{http://www.efinixinc.com/enf_proj}bitstream_generation/{http://www.efinixinc.com/enf_proj}param')}
    cmd=['C:/Efinity/2026.1/bin/efx_pgm.exe','--interface_designer_settings',f'outflow/{name}_or.ini',
         '--periph',f'outflow/{name}.lpf','--family','Titanium','--device','Ti60F225',
         '--source',f'work_pnr/{name}.lbf','--dest',f'outflow/{name}.hex']
    cmd += ['--'+k+'='+params[k] for k in allowed]
stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
log=root/'validation'/f'{flow}_{stamp}.log'
with log.open('wb') as out:
    p=subprocess.run(cmd,cwd=root,env=env,stdout=out,stderr=subprocess.STDOUT)
print(f'{flow}: exit={p.returncode}, log={log}')
print(log.read_text(errors='replace')[-2200:])
sys.exit(p.returncode)
