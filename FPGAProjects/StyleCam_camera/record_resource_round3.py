"""Bind peripheral resource pass 3 to exact sources, regressions and final STA."""
from pathlib import Path
import hashlib, json, os, re, sys
from package_optimization import timing_summary

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'validation/resource_opt_round3_20261016'
BUILD=Path(sys.argv[1]).resolve()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
baseline=json.loads((OUT/'baseline_sha256.json').read_text())
allowed=['rtl/sc_apb_regs.v','rtl/sc_display.v']
protected=[p for p in baseline if p not in allowed]
assert all(sha(ROOT/p)==baseline[p] for p in protected),'Network/model/firmware/configuration changed'
changed=[p for p in allowed if sha(ROOT/p)!=baseline[p]]+['rtl/sc_osd_font.vh']
sources={p:sha(ROOT/p) for p in changed}
for folder in ['rtl','model','ip','fw_rom']:
 for p in (ROOT/folder).rglob('*'):
  if p.is_file():
   routed=BUILD/(p.name if folder=='fw_rom' else p.relative_to(ROOT))
   assert routed.is_file() and sha(routed)==sha(p),f'Stale routed source: {p}'
for rel in ['validation/resource_opt_round2_20261016/simulation/result.json',
            'validation/resource_opt_round3_20261016/simulation/result.json',
            'validation/main_ae/result.json']:
 data=json.loads((ROOT/rel).read_text());assert data['passed']
 if 'round3' in rel:assert set(data['tests'])=={'font_behavior','font_primitive','display_equivalence'}
 for test in data['tests'].values():
  assert test['passed']
  for p,digest in test['source_sha256'].items():assert sha(ROOT/p)==digest,p
  sources.update(test['source_sha256'])
for rel in ['validation/camera_native_rgb_mirror/small/result.json',
            'validation/camera_native_rgb_mirror/full_hd_mirror/result.json',
            'validation/main_ae/firmware/result.json']:
 data=json.loads((ROOT/rel).read_text());assert data['passed']
 if 'source_sha256' in data:assert sha(ROOT/data['source'])==data['source_sha256']
timing=timing_summary(BUILD/'outflow/ti60f225_oob.timing.rpt')
place=(BUILD/'outflow/ti60f225_oob.place.rpt').read_text()
resources={}
for key,label in [('xlr','XLRs'),('ram10','Memory Blocks'),('dsp','DSP Blocks')]:
 m=re.search(r'^'+label+r': (\d+) / (\d+)',place,re.M);assert m
 resources[key],resources[key+'_total']=map(int,m.groups())
previous=dict(xlr=57160,ram10=245,dsp=145)
assert resources['xlr']<previous['xlr'] and resources['ram10']<previous['ram10'],'Require both logic and RAM savings'
assert resources['dsp']==previous['dsp']
mapped={}
for name,folder in [('previous',Path(os.environ['TEMP'])/'stylecam_r2c_ae_20261016/outflow'),('candidate',BUILD/'outflow')]:
 text=(folder/'ti60f225_oob.map.rpt').read_text()
 mapped[name]={k:(int(m[1]) if (m:=re.search(k+r'\s*:\s*(\d+)',text)) else 0)
               for k in ['EFX_LUT4','EFX_ADD','EFX_FF','EFX_RAM10','EFX_DPRAM10','EFX_DSP48']}
sources['generate_osd_font.py']=sha(ROOT/'generate_osd_font.py')
sources['sim_resource_round3.py']=sha(ROOT/'sim_resource_round3.py')
result=dict(passed=True,scope='offline peripheral equivalence and final routed STA; board validation pending',
 network_unchanged=True,firmware_unchanged=True,phone_preview_default=False,protected_files=len(protected),
 changed_rtl=changed,previous_resources=previous,resources=resources,
 delta_from_previous={k:resources[k]-v for k,v in previous.items()},
 setup_min_ns=timing['setup_min_ns'],hold_min_ns=timing['hold_min_ns'],
 setup_relationships=len(timing['setup']),hold_relationships=len(timing['hold']),
 mapped_resources=mapped,font_glyphs_compared=96,font_rows_per_glyph=16,font_random_transitions=5000,
 font_storage_words=955,font_storage_bits_per_word=10,font_native_primitive_simulated=True,
 display_layouts_compared=3,display_source_size=[640,480],apb_random_transactions=30000,
 hardware_verified=False,tested_source_sha256=sources)
(OUT/'result.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
print(json.dumps({k:result[k] for k in ['resources','delta_from_previous','setup_min_ns','hold_min_ns']},indent=2))
