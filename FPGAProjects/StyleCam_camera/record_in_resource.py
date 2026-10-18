"""Bind exact-IN resource optimization to golden regressions and routed sources."""
from pathlib import Path
import hashlib,json,os,re,sys
from package_optimization import timing_summary

ROOT=Path(__file__).resolve().parent;OUT=ROOT/'validation/in_resource_20261017'
BUILD=Path(sys.argv[1]).resolve();sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
baseline=json.loads((OUT/'baseline_sha256.json').read_text())
changed=['rtl/sc_in_alu.v','rtl/sc_in_refresh.v']
protected=[p for p in baseline if p not in changed]
for p in protected:assert sha(ROOT/p)==baseline[p],f'Protected model/convolution/firmware/config changed: {p}'
firmware=ROOT/'embedded_sw/soc/software/standalone/stylecam/build/stylecam.bin'
previous_manifest=json.loads((ROOT.parent/'烧录文件/20261016_RISCV11_Main_AE_Resource3_Candidate/manifest.json').read_text(encoding='utf-8'))
assert sha(firmware)==previous_manifest['files']['stylecam.bin']['sha256'],'Firmware binary differs from resource pass 3'
for folder in ['rtl','model','ip','fw_rom']:
 for p in (ROOT/folder).rglob('*'):
  if p.is_file():
   routed=BUILD/(p.name if folder=='fw_rom' else p.relative_to(ROOT))
   assert routed.is_file() and sha(routed)==sha(p),f'Stale routed source: {p}'
sources={p:sha(ROOT/p) for p in changed}
unit=json.loads((OUT/'simulation/alu.json').read_text());assert unit['passed']
assert sum(t['vectors'] for t in unit['tests'].values())==337520
for test in unit['tests'].values():
 for p,digest in test['source_sha256'].items():assert sha(ROOT/p)==digest,p
 tested=test['source_sha256'].get('rtl/sc_in_alu.v',test['source_sha256'].get('validation/in_resource_20261017/alu_new.v'))
 assert tested==sha(ROOT/'rtl/sc_in_alu.v')
 sources.update(test['source_sha256'])
integration_result_paths={}
for name in ['math','engine','vga']:
 paths=[OUT/f'integrated/{name}/result.json']
 if name=='vga':paths.insert(0,OUT/'integrated_parallel/vga/result.json')
 for path in paths:
  if not path.is_file():continue
  data=json.loads(path.read_text())
  if data.get('passed') and all((ROOT/p).is_file() and sha(ROOT/p)==digest
     for key in ['source_sha256','vector_sha256'] for p,digest in data[key].items()):break
 else:raise AssertionError(f'No current passing {name} result')
 integration_result_paths[name]=path.relative_to(ROOT).as_posix()
 for key in ['source_sha256','vector_sha256']:
  for p,digest in data[key].items():assert sha(ROOT/p)==digest,p
 sources.update(data['source_sha256']);sources.update(data['vector_sha256'])
 if name=='math':assert data['vectors']==3273 and data['VGA_statistics']
 if name=='engine':assert data['pixels_exact']==6912 and data['coefficients_exact']==936
 if name=='vga':
  assert data['pixels_exact']==307200 and data['simulated_job_ms']<1000/30
  vga=data
rom=json.loads((ROOT/'validation/serial_constants_rtl/result.json').read_text());assert rom['passed']
assert rom['vga_words_exact']==816 and rom['coefficients_exact']==816
for p,digest in rom['source_sha256'].items():assert sha(ROOT/'rtl'/p)==digest,p
for p in ['compact_in_constants.py','sim_in_resource.py','sim_in_integrated.py','sim_serial_constants.py',
          'model/in_constants.mem.ec0','model/in_constants.mem.ec1']:
 sources[p]=sha(ROOT/p)
timing=timing_summary(BUILD/'outflow/ti60f225_oob.timing.rpt')
text=(BUILD/'outflow/ti60f225_oob.place.rpt').read_text();resources={}
for key,label in [('xlr','XLRs'),('ram10','Memory Blocks'),('dsp','DSP Blocks')]:
 m=re.search(r'^'+label+r': (\d+) / (\d+)',text,re.M);assert m
 resources[key],resources[key+'_total']=map(int,m.groups())
previous=dict(xlr=57115,ram10=244,dsp=145)
assert resources['xlr']<previous['xlr'] and resources['ram10']<previous['ram10']
assert resources['dsp']==145
result=dict(passed=True,scope='exact dynamic-IN hardware and final routed STA; board validation pending',
 resource_pass=4,network_unchanged=False,model_unchanged=True,convolution_unchanged=True,
 IN_rules_unchanged=True,firmware_unchanged=True,phone_preview_default=False,
 firmware_binary_bytes=firmware.stat().st_size,firmware_binary_sha256=sha(firmware),
 protected_files=len(protected),changed_rtl=changed,previous_resources=previous,resources=resources,
 delta_from_previous={k:resources[k]-v for k,v in previous.items()},
 setup_min_ns=timing['setup_min_ns'],hold_min_ns=timing['hold_min_ns'],
 setup_relationships=len(timing['setup']),hold_relationships=len(timing['hold']),
 alu_integer_vectors=337520,IN_real_statistics_vectors=3273,ROM_words_exact=816,
 three_style_pixels_exact=6912,three_style_coefficients_exact=936,VGA_pixels_exact=307200,
 simulated_VGA_job_ms=vga['simulated_job_ms'],previous_simulated_VGA_job_ms=30.45023,
 constants_in_external_Flash=False,hardware_verified=False,tested_source_sha256=sources)
result['integration_result_paths']=integration_result_paths
(OUT/'result.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
print(json.dumps({k:result[k] for k in ['resources','delta_from_previous','setup_min_ns','hold_min_ns','simulated_VGA_job_ms']},indent=2))
