"""Curate portable source + chosen runnable delivery; omit teacher weights and unrelated/local-old projects."""
import argparse, datetime, hashlib, json, pathlib, zipfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser();ap.add_argument('--deployment',required=True);ap.add_argument('--output',default='release/tristyle_first_version.zip');a=ap.parse_args()
dep=ROOT/a.deployment; archive=ROOT/a.output;archive.parent.mkdir(exist_ok=True)
files=set()
def add(p):
    if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.part'): files.add(p)
for pattern in ('*.py','*.md','requirements.txt'):
    for p in ROOT.glob(pattern):add(p)
for folder in ('claude_impl','continuation_impl','supervisor','sources','external/depth_v2'):
    for p in (ROOT/folder).rglob('*'):
        if p.suffix.lower() in ('.py','.md','.json','.jsonl','.txt','.html') or p.name.startswith('LICENSE'):add(p)
add(ROOT/'external/adain_arch.py')
for folder in ('data/test','data/references','data/claude_targets/painterly_p1_provenance'):
    for p in (ROOT/folder).rglob('*'):add(p)
for pattern in ('data/*.json','data/continuation_depth/config.json','data/video/train_pairs/manifest.json'):
    for p in ROOT.glob(pattern):add(p)
for p in dep.rglob('*'):
    if p.suffix in ('.py','.pt','.ts','.bin','.json','.md','.jpg','.png','.mp4') or p.name=='PIPELINE_COMPLETED.json':add(p)
# Exact run configs, source snapshots and growing-data schedules, without multi-GB optimizer history.
for run in (ROOT/'runs').iterdir():
    if not run.is_dir():continue
    for name in ('config.json','dataset_schedule.jsonl','finished.json'):add(run/name)
    for p in (run/'source').rglob('*.py'):add(p)
manifest={str(p.relative_to(ROOT)).replace('\\','/'):{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(files)}
record={'created':datetime.datetime.now().astimezone().isoformat(),'selected_deployment':a.deployment,'files':manifest,
    'excluded':'All teacher binary weights, raw COCO corpus, training target PNG cache, depth maps and optimizer/checkpoint history. Existing full workspace retains these. Download records, legal original manifests, reference paintings, fixed17 tests, source snapshots and chosen inference artifacts are included.',
    'reproducibility':'Inference is directly executable using included weights. Re-training requires fetching originals/teachers and regenerating caches; exact CUDA bit replay is not guaranteed. Artistic acceptance is separate.'}
manifest_path=archive.with_suffix('.manifest.json');manifest_path.write_text(json.dumps(record,indent=1),encoding='utf-8')
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=5) as z:
    for p in sorted(files):z.write(p,str(p.relative_to(ROOT)))
    z.write(manifest_path,'RELEASE_MANIFEST.json')
result={'archive':str(archive),'bytes':archive.stat().st_size,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'files':len(files)}
archive.with_suffix('.sha256.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
