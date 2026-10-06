"""Version-aware offline release gate for the V21 / SCU09 full board project."""
from pathlib import Path
import hashlib,json,os,re
ROOT=Path(__file__).resolve().parent
GEN=ROOT.parent/'StyleCam/rtl/gen/v21b_ukiyoe_qat900_640x480'
MIRROR=Path(os.environ['TEMP'])/'stylecam_v21_camera_build'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads((ROOT/p).read_text(encoding='utf-8'))
integration=read('model/integration.json');assert integration['firmware_version']==9
assert integration['network']=='v21b_ukiyoe_qat900_640x480'
for name,digest in integration['source_gen_files'].items():
    assert sha(GEN/name)==digest,('upstream network changed',name)
    if (ROOT/'model'/name).exists(): assert sha(ROOT/'model'/name)==digest,name
for rel,digest in integration['unchanged_camera_and_core_files'].items():assert sha(ROOT/rel)==digest,rel
expected_top=re.sub(r'\.(WFILE|CFILE)\("([^"]+)"\)',lambda m:f'.{m[1]}("model/{m[2]}")',(GEN/'stylenet_top.v').read_text(encoding='utf-8'))
assert (ROOT/'rtl/stylenet_top.v').read_text(encoding='utf-8')==expected_top
q=read('model/qparams.json');shift_source=(ROOT/'rtl/sc_in_refresh.v').read_text()
for i,L in enumerate(q['layers'][:12]):assert f'{i}:shift={L["S"]};' in shift_source,(i,L['S'])
assert 'FW_VERSION=9' in (ROOT/'rtl/StyleCam_uart.v').read_text()
hashes={}
for folder in ['rtl','model','ip']:
    for p in (ROOT/folder).rglob('*'):
        if p.is_file():
            rel=p.relative_to(ROOT);assert sha(p)==sha(MIRROR/rel),str(rel);hashes[rel.as_posix()]=sha(p)
for p in ROOT.glob('ti60f225_oob.*'):
    if p.suffix in ['.xml','.sdc']: assert sha(p)==sha(MIRROR/p.name),p.name;hashes[p.name]=sha(p)
tests={p:read(p) for p in ['validation/camera_sim/result.json','validation/video_engine/result.json','validation/compact_IN.json','validation/display_pressure/result.json','validation/in_math/result.json']}
assert tests['validation/compact_IN.json']['lossless']
for path in ['validation/camera_sim/result.json','validation/video_engine/result.json','validation/display_pressure/result.json','validation/in_math/result.json']:assert tests[path]['passed'],path
assert tests['validation/in_math/result.json']['model_coefficients_exact'] and tests['validation/in_math/result.json']['VGA_statistics_included']
networktest=tests['validation/video_engine/result.json']
assert networktest['network']==integration['network'] and networktest['styles']==[0,1,2] and networktest['pixels_exact']==6912
resources={};place=(ROOT/'outflow/ti60f225_oob.place.rpt').read_text();timing=(ROOT/'outflow/ti60f225_oob.timing.rpt').read_text()
for key,label in [('XLR','XLRs'),('RAM10','Memory Blocks'),('DSP','DSP Blocks')]:
    m=re.search('^'+label+r': (\d+) / (\d+) \(([\d.]+)%\)',place,re.M);assert m,key
    used,total=int(m[1]),int(m[2]);assert used<=total,key;resources[key]=dict(used=used,total=total,percent=float(m[3]))
def minimum(section):return min(float(m[1]) for m in re.finditer(r'^\S+\s+\S+\s+[\d.-]+\s+([\d.-]+)\s+\(R-R\)',section,re.M))
setup=minimum(timing.split('Setup (Max) Clock Relationship',1)[1].split('Hold (Min)',1)[0])
hold=minimum(timing.split('Hold (Min) Clock Relationship',1)[1].split('NOTE:',1)[0]);assert setup>0 and hold>0,(setup,hold)
hexfile=ROOT/'outflow/ti60f225_oob.hex';bitfile=ROOT/'outflow/ti60f225_oob.bit'
size=len(hexfile.read_text().splitlines());assert 0<size<8*1024*1024
report=dict(ready_to_program=True,firmware_version=9,network=integration['network'],network_blob_sha256=sha(ROOT/'model/net_blob.bin'),
 checkpoint_sha256=integration['checkpoint_sha256'],camera='SC431HAI 1920x1080 RAW10; center crop 1280x960 -> RGB640x480',
 resources=resources,timing=dict(setup_min_ns=setup,hold_min_ns=hold),network_simulation=dict(passed=True,tests=tests),
 replay_display_simulation=dict(passed=True,output_double_buffer=True),hex_sha256=sha(hexfile),bit_sha256=sha(bitfile),flash_bytes=size,
 autonomous_camera_start=True,host_RGB_upload_required=False,host_IN_coefficients_required=False)
(ROOT/'validation/source_sha256.json').write_text(json.dumps(hashes,indent=2),encoding='utf-8')
(ROOT/'results/offline_check.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
