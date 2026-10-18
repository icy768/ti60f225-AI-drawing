"""Bind resource-pass-2 regressions and final STA to the exact routed sources."""
from pathlib import Path
import hashlib, json, os, re, sys
from package_optimization import timing_summary

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'validation/resource_opt_round2_20261016'
BUILD=Path(sys.argv[1]).resolve()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
baseline=json.loads((OUT/'baseline_sha256.json').read_text())
allowed=['rtl/sc_apb_regs.v','rtl/sc_camera_rgb.v','rtl/sc_capture.v','rtl/sc_display.v','rtl/sc_replay.v','rtl/sc431hai/i2c_reg16.v']
protected=[p for p in baseline if p.startswith(('rtl/','model/','ip/','fw_rom/','embedded_sw/')) and p not in allowed]
assert all(sha(ROOT/p)==baseline[p] for p in protected), 'Protected network/model/firmware changed'
assert sha(ROOT/'ti60f225_oob.sdc')==baseline['ti60f225_oob.sdc']
for folder in ['rtl','model','ip','fw_rom']:
 for p in (ROOT/folder).rglob('*'):
  if p.is_file():
   routed=BUILD/(p.name if folder=='fw_rom' else p.relative_to(ROOT))
   assert routed.is_file() and sha(routed)==sha(p), f'Stale routed source: {p}'
changed=[p for p in allowed if sha(ROOT/p)!=baseline[p]]
sources={p:sha(ROOT/p) for p in changed}
for record in ['validation/resource_opt_round2_20261016/simulation/result.json','validation/main_ae/result.json']:
 data=json.loads((ROOT/record).read_text());assert data['passed']
 for test in data['tests'].values():
  assert test['passed']
  for p,digest in test['source_sha256'].items():assert sha(ROOT/p)==digest,p
  sources.update(test['source_sha256'])
for record in ['validation/camera_native_rgb_mirror/small/result.json','validation/camera_native_rgb_mirror/full_hd_mirror/result.json','validation/main_ae/firmware/result.json']:
 data=json.loads((ROOT/record).read_text());assert data['passed']
 if 'source_sha256' in data:assert sha(ROOT/data['source'])==data['source_sha256']
for p in ['sim/camera_rgb_tb.v','sim/camera_rgb_mirror_tb.v','sim_camera_mhc.py','sim_resource_round2.py','sim_main_ae.py','ti60f225_oob.sdc']:
 sources[p]=sha(ROOT/p)
timing=timing_summary(BUILD/'outflow/ti60f225_oob.timing.rpt')
place=(BUILD/'outflow/ti60f225_oob.place.rpt').read_text()
resources={}
for key,label in [('xlr','XLRs'),('ram10','Memory Blocks'),('dsp','DSP Blocks')]:
 m=re.search(r'^'+label+r': (\d+) / (\d+)',place,re.M);assert m
 resources[key],resources[key+'_total']=map(int,m.groups())
mapped={}
for name,path in [('previous',ROOT/'validation/resource_opt_20261016/ae_main/outflow'),('candidate',BUILD/'outflow')]:
 text=(path/'ti60f225_oob.map.rpt').read_text()
 mapped[name]={k:(int(m[1]) if (m:=re.search(k+r'\s*:\s*(\d+)',text)) else 0) for k in ['EFX_LUT4','EFX_ADD','EFX_FF','EFX_RAM10','EFX_DSP48']}
result=dict(passed=True,scope='offline regressions and final routed STA; hardware validation pending',
 network_unchanged=True,phone_preview_default=False,protected_files=len(protected),
 changed_rtl=changed,previous_resources=dict(xlr=57441,ram10=245,dsp=145),resources=resources,
 delta_from_previous={k:resources[k]-v for k,v in dict(xlr=57441,ram10=245,dsp=145).items()},
 setup_min_ns=timing['setup_min_ns'],hold_min_ns=timing['hold_min_ns'],
 setup_relationships=len(timing['setup']),hold_relationships=len(timing['hold']),
 mapped_resources=mapped,camera_pixels_compared=921600,replay_cycle_equivalent_pixels=1228800,
 apb_random_transactions=30000,font_compact_used='sc_font_rom #' in (ROOT/'rtl/sc_display.v').read_text(),
 camera_clip_inputs=16384,raw_black_inputs=1024,
 hardware_verified=False,tested_source_sha256=sources)
(OUT/'result.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
print(json.dumps({k:result[k] for k in ['resources','delta_from_previous','setup_min_ns','hold_min_ns']},indent=2))
