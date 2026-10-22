"""Vendor initial-content update on local B, with exact old-ROM roundtrip."""
from pathlib import Path
import os,json,hashlib,shutil,subprocess,xml.etree.ElementTree as E,datetime
R=Path(__file__).resolve().parent;O=R/'DP3/FW_PATCH';B=R/'DP3/D1B60';L=O/'layout';N='ti60f225_oob'
assert json.loads((O/'BINARY_RESULT.json').read_text())['passed']
assert not L.exists();L.mkdir()
for n in [N+'.xml','work_pnr/'+N+'.lbf',*[f'outflow/{N}.{s}' for s in ['place','raminfo.pb','lpf']],f'outflow/{N}_or.ini']:
 p=L/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(B/n,p)
env=dict(os.environ);env.update(EFINITY_HOME='D:/',EFXPGM_HOME='D:/pgm');env['PATH']='D:/bin;'+env['PATH']
ns='{http://www.efinixinc.com/enf_proj}';params={x.get('name'):x.get('value') for x in E.parse(L/(N+'.xml')).findall('.//'+ns+'bitstream_generation/'+ns+'param')}
keys=['mode','width','enable_roms','spi_low_power_mode','io_weak_pullup','oscillator_clock_divider','enable_crc_check','bitstream_compression','active_capture_clk_edge','release_tri_then_reset','enable_external_master_clock','jtag_usercode']
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();steps=[];rows=[]
def run(args,log):
 with log.open('w',encoding='utf-8') as stream:rc=subprocess.run(args,cwd=L,env=env,stdout=stream,stderr=subprocess.STDOUT).returncode
 steps.append(dict(args=args,rc=rc,log=str(log.relative_to(R))));assert rc==0,str(log)
for label,source,rom,reference in [('patched','work_pnr',O/'fw_rom',None),('idempotent','patched',O/'fw_rom',L/'patched'),('restored','patched',B/'fw_rom',B/'outflow')]:
 out=L/label;out.mkdir()
 args=['D:/bin/efx_bram_edit.exe','-j',N+'.xml','-i',f'outflow/{N}.raminfo.pb','-p',f'outflow/{N}.place','-l',f'{source}/{N}.lbf','-o',f'{label}/{N}.lbf','-f','Titanium','-m','update']
 for lane in range(4):args+=['-b',f'cpu/u_EfxSapphireSoc/system_ramA_logic/ram_symbol{lane},{(rom/f"EfxSapphireSoc.v_toplevel_system_ramA_logic_ram_symbol{lane}.bin").resolve().as_posix()}']
 run(args,out/'bram_update.log')
 args=['D:/bin/efx_pgm.exe','--interface_designer_settings',f'outflow/{N}_or.ini','--periph',f'outflow/{N}.lpf','--family','Titanium','--device','Ti60F225','--source',f'{label}/{N}.lbf','--dest',f'{label}/{N}.hex']+['--'+k+'='+params[k] for k in keys]
 run(args,out/'generate.log');compares={}
 for ext in ['bit','hex']:
  p=out/f'{N}.{ext}';v=bytes.fromhex(p.read_text());base=bytes.fromhex((B/f'outflow/{N}.{ext}').read_text())
  compares[ext]=dict(bytes=p.stat().st_size,sha256=sha(p),payload_sha256=hashlib.sha256(v[256:]).hexdigest(),changed_decoded_bytes_vs_B=sum(a!=b for a,b in zip(v[256:],base[256:])),full_file_equal_to_B=p.read_bytes()==(B/f'outflow/{N}.{ext}').read_bytes())
  if reference:
   expected=bytes.fromhex((reference/f'{N}.{ext}').read_text());assert len(v)==len(expected) and v[256:]==expected[256:]
   compares[ext]['configuration_payload_exact_to_reference']=True
 rows.append(dict(label=label,reference=str(reference) if reference else None,files=compares))
# Inputs to updater are identical B layout/constraints. CPU byte-lane initial
# values are the only requested edit; restoration proves the payload returns.
input_exact={n:sha(L/n)==sha(B/n) for n in [N+'.xml','work_pnr/'+N+'.lbf',f'outflow/{N}.place',f'outflow/{N}.raminfo.pb',f'outflow/{N}.lpf',f'outflow/{N}_or.ini']}
assert all(input_exact.values())
result=dict(passed=True,time=datetime.datetime.now().astimezone().isoformat(),rows=rows,steps=steps,input_layout_files_exact=input_exact,only_requested_edit='CPU system_ramA four byte-lane BRAM initialization; no RTL, VG ROM, routing, netlist or constraints edit',payload_localization='Vendor updater targeting named CPU BRAMs plus exact original-payload restoration; compressed/encrypted payload byte ranges are not independently decoded into physical regions.',full_file_A_identity_pass=False,header_note='First 256 decoded text-header bytes may differ; no header rewriting or SHA normalization',resource_timing='Referenced from unchanged local B routed layout:56824XLR/243RAM10/145DSP,+.240/+.026ns; not new PnR measurement',board_tested=False,full_boot_verified=False,adopted=False)
(O/'ROM_RESULT.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))
