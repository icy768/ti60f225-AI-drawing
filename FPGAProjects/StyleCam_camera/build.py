"""Run Efinity in an ASCII temp mirror; copy evidence back to this workspace."""
from pathlib import Path
import os,sys,shutil,subprocess,datetime,xml.etree.ElementTree as E
ROOT=Path(__file__).resolve().parent
BUILD=Path(os.environ.get('STYLECAM_BUILD_DIR',Path(os.environ['TEMP'])/'stylecam_v21_camera_build'))
BUILD.mkdir(exist_ok=True)
flow=sys.argv[1]; assert flow in ['interface','map','pnr','pgm']
for folder in ['rtl','model','ip']:
    shutil.copytree(ROOT/folder,BUILD/folder,dirs_exist_ok=True)
for p in ROOT.glob('ti60f225_oob.*'): shutil.copy2(p,BUILD/p.name)
# Sapphire on-chip RAM images (firmware), read by $readmemb relative to the project directory
for p in (ROOT/'fw_rom').glob('*.bin'): shutil.copy2(p,BUILD/p.name)
home=Path(os.environ.get('STYLECAM_EFINITY','D:/ELS/efinity/2026.1')); name='ti60f225_oob'
env=os.environ.copy(); env.update(EFINITY_HOME=home.as_posix(),PYTHONHOME=str(home/'python311'),PROCESSOR_ARCHITECTURE='AMD64',PYTHONDONTWRITEBYTECODE='1')
env['EFINITY_USER_DIR_INI']=os.environ['LOCALAPPDATA']+'/efinity/user_dir.ini'
for key,folder in [('EFXPT_HOME','pt'),('EFXPGM_HOME','pgm'),('EFXDBG_HOME','debugger'),('EFXIPM_HOME','ipm')]: env[key]=(home/folder).as_posix()
env['PATH']=str(home/'python311/bin')+';'+str(home/'bin')+';'+env['PATH']
if flow!='pgm': cmd=[str(home/'bin/efx_run.bat'),name+'.xml','--flow',flow]
else:
    allowed=['mode','width','enable_roms','spi_low_power_mode','io_weak_pullup','oscillator_clock_divider','bitstream_compression','enable_external_master_clock','active_capture_clk_edge','jtag_usercode','release_tri_then_reset']
    params={x.get('name'):x.get('value') for x in E.parse(ROOT/(name+'.xml')).findall('.//{http://www.efinixinc.com/enf_proj}bitstream_generation/{http://www.efinixinc.com/enf_proj}param')}
    cmd=[str(home/'bin/efx_pgm.exe'),'--interface_designer_settings',f'outflow/{name}_or.ini','--periph',f'outflow/{name}.lpf','--family','Titanium','--device','Ti60F225','--source',f'work_pnr/{name}.lbf','--dest',f'outflow/{name}.hex']
    cmd+=['--'+k+'='+params[k] for k in allowed]
log=ROOT/'validation'/f'{flow}_{datetime.datetime.now():%Y%m%d_%H%M%S}.log'
print('Build:',BUILD,'Log:',log,flush=True)
with log.open('wb') as f: result=subprocess.run(cmd,cwd=BUILD,env=env,stdout=f,stderr=subprocess.STDOUT)
print(log.read_text(errors='replace')[-4500:]); print('exit:',result.returncode)
if (BUILD/'outflow').exists(): shutil.copytree(BUILD/'outflow',ROOT/'outflow',dirs_exist_ok=True)
sys.exit(result.returncode)
