"""Use vendor PGM to compare opaque LBF contents, preserving all failed exact checks."""
from pathlib import Path
import os,json,subprocess,hashlib,xml.etree.ElementTree as E
R=Path(__file__).resolve().parent;O=R/'DP3/FW_CRC';L=O/'layout';B=R/'DP3/D1B60';name='ti60f225_oob';env=dict(os.environ);env['EFINITY_HOME']='D:/'
args=['D:/bin/efx_bram_edit.exe','-j',name+'.xml','-i',f'outflow/{name}.raminfo.pb','-p',f'outflow/{name}.place','-l',f'D1_crc_firmware/{name}.lbf','-o','../restore_original.lbf','-f','Titanium','-m','update']
for i in range(4):args+=['-b',f'cpu/u_EfxSapphireSoc/system_ramA_logic/ram_symbol{i},{(B/f"fw_rom/EfxSapphireSoc.v_toplevel_system_ramA_logic_ram_symbol{i}.bin").resolve().as_posix()}']
with (O/'restore_original.log').open('w',encoding='utf-8') as f:rc=subprocess.run(args,cwd=L,env=env,stdout=f,stderr=subprocess.STDOUT).returncode
assert rc==0
ns='{http://www.efinixinc.com/enf_proj}';params={x.get('name'):x.get('value') for x in E.parse(L/(name+'.xml')).findall('.//'+ns+'bitstream_generation/'+ns+'param')}
allowed=['mode','width','enable_roms','spi_low_power_mode','io_weak_pullup','oscillator_clock_divider','enable_crc_check','bitstream_compression','active_capture_clk_edge','release_tri_then_reset','enable_external_master_clock','jtag_usercode']
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
rows=[]
for label,reference in [('new_idempotent',L/'D1_crc_firmware'),('restore_original',B/'outflow')]:
    out=O/(label+'_pgm');assert not out.exists();out.mkdir()
    args=['D:/bin/efx_pgm.exe','--interface_designer_settings',f'outflow/{name}_or.ini','--periph',f'outflow/{name}.lpf','--family','Titanium','--device','Ti60F225','--source',f'../{label}.lbf','--dest',f'../{label}_pgm/{name}.hex']+['--'+k+'='+params[k] for k in allowed]
    with (out/'generate.log').open('w',encoding='utf-8') as f:rc=subprocess.run(args,cwd=L,env=env,stdout=f,stderr=subprocess.STDOUT).returncode
    assert rc==0
    compare={}
    for ext in ['bit','hex']:
        a=bytes.fromhex((out/f'{name}.{ext}').read_text());b=bytes.fromhex((reference/f'{name}.{ext}').read_text())
        assert len(a)==len(b) and a[256:]==b[256:]
        compare[ext]=dict(after_text_header_exact=True,full_sha_equal=sha(out/f'{name}.{ext}')==sha(reference/f'{name}.{ext}'),payload_sha256=hashlib.sha256(a[256:]).hexdigest())
    rows.append(dict(case=label,compared_to=str(reference.relative_to(R)),results=compare))
(O/'PAYLOAD_ROUNDTRIP.json').write_text(json.dumps(dict(passed=True,rows=rows,A_identity_pass=False,scope='Local B firmware update idempotence and original restoration through vendor-generated configuration payloads; full container SHA checks remain false',opaque_lbf_note='LBF starts LBFEncComp0000001; changed opaque bytes do not by themselves establish changed logical configuration; vendor PGM payloads were compared instead. No decryption or container header normalization.'),indent=2),encoding='utf-8')
print('PASS local B new-ROM idempotent and old-ROM restored configuration payloads; not full-file A identity')
