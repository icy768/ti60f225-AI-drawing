"""Finish the local B-layout CRC remedy after documenting container metadata."""
from pathlib import Path
import os,json,subprocess,hashlib,datetime,xml.etree.ElementTree as E
R=Path(__file__).resolve().parent;O=R/'DP3/FW_CRC';L=O/'layout';B=R/'DP3/D1B60';name='ti60f225_oob'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
old=B/f'work_pnr/{name}.lbf';identity=L/f'identity_original_firmware/{name}.lbf'
assert old.read_bytes()==identity.read_bytes()
diff={}
for ext in ['bit','hex']:
    a=bytes.fromhex((B/f'outflow/{name}.{ext}').read_text());b=bytes.fromhex((L/f'identity_original_firmware/{name}.{ext}').read_text())
    indices=[i for i,(x,y) in enumerate(zip(a,b)) if x!=y]
    assert len(a)==len(b) and a[256:]==b[256:] and all(i<256 for i in indices)
    diff[ext]=dict(full_file_sha_equal=False,decoded_size=len(a),changed_offsets=indices,all_changes_in_text_header_first256=True,configuration_payload_after256_exact=True)
# A's historical byte-identity criterion is NOT passed by this B-layout diagnostic.
# Original failed exact-container attempt and its logs remain untouched.
out=L/'D1_crc_firmware';assert not out.exists();out.mkdir()
env=dict(os.environ);env.update(EFINITY_HOME='D:/',EFXPGM_HOME='D:/pgm');env['PATH']='D:/bin;'+env['PATH']
args=['D:/bin/efx_bram_edit.exe','-j',name+'.xml','-i',f'outflow/{name}.raminfo.pb','-p',f'outflow/{name}.place','-l',f'work_pnr/{name}.lbf','-o',f'D1_crc_firmware/{name}.lbf','-f','Titanium','-m','update']
for i in range(4):args+=['-b',f'cpu/u_EfxSapphireSoc/system_ramA_logic/ram_symbol{i},{(O/f"D1_crc_only/fw_rom/EfxSapphireSoc.v_toplevel_system_ramA_logic_ram_symbol{i}.bin").resolve().as_posix()}']
steps=[]
def run(args,log):
    with log.open('w',encoding='utf-8') as f:rc=subprocess.run(args,cwd=L,env=env,stdout=f,stderr=subprocess.STDOUT).returncode
    steps.append(dict(args=args,rc=rc,log=str(log.relative_to(R))));assert rc==0
run(args,out/'bram_update.log')
ns='{http://www.efinixinc.com/enf_proj}';params={x.get('name'):x.get('value') for x in E.parse(L/(name+'.xml')).findall('.//'+ns+'bitstream_generation/'+ns+'param')}
# Explicitly include the same enable_crc_check option as the original pgm invocation.
allowed=['mode','width','enable_roms','spi_low_power_mode','io_weak_pullup','oscillator_clock_divider','enable_crc_check','bitstream_compression','active_capture_clk_edge','release_tri_then_reset','enable_external_master_clock','jtag_usercode']
args=['D:/bin/efx_pgm.exe','--interface_designer_settings',f'outflow/{name}_or.ini','--periph',f'outflow/{name}.lpf','--family','Titanium','--device','Ti60F225','--source',f'D1_crc_firmware/{name}.lbf','--dest',f'D1_crc_firmware/{name}.hex']+['--'+k+'='+params[k] for k in allowed]
run(args,out/'generate_files.log')
result=dict(time=datetime.datetime.now().astimezone().isoformat(),status='LOCAL_B_CRC_REMEDY_FILES_READY_PENDING_SUPERVISION',identity_lbf_exact=True,identity_containers=diff,A_identity_pass=False,original_exact_container_gate_not_passed=True,metadata_note='Textual Generated time / Project directory in first256 decoded bytes differ; no normalization or timestamp rewriting applied. Configuration payload after256 was exact. This is local B layout, not historical A.',steps=steps,files={p.relative_to(L).as_posix():dict(bytes=p.stat().st_size,sha256=sha(p)) for p in out.glob(name+'.*')},new_compiler_firmware=True,new_firmware_bytes=13458,full_system_boot_verified=False,board_tested=False,adopted=False,resource_timing='Only BRAM initial-content update of local B routed layout; no routing/PnR rerun. Resource/timing referenced from original B; not newly measured.')
(O/'CRC_REMEDY_RESULT.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))
