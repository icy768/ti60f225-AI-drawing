import json,pathlib,shutil,hashlib
from PIL import Image
from prepare_data import main as prepare,save_gallery
ROOT=pathlib.Path(__file__).resolve().parent
spec={451090:'water_day',491725:'water_night',230362:'sky_storm',221502:'plants_garden',221754:'architecture_street',289222:'edges_signals',546717:'person_indoor',473237:'person_face',462614:'indoor_bathroom',182441:'water_waves',539883:'edges_buildings'}
ann=json.loads((ROOT/'data/raw/instances_val2017.json').read_text());meta={o['id']:o for o in ann['images']};dst=ROOT/'data/test';dst.mkdir(exist_ok=True);records=[]
for oid,name in spec.items():
    o=meta[oid];assert o['license'] in [4,5,8]
    p=ROOT/'data/raw/val2017'/o['file_name']
    if not p.exists():raise RuntimeError('Missing fixed test '+str(oid))
    q=dst/(name+'.png');Image.open(p).convert('RGB').save(q)
    records.append({**o,'test_file':str(q.relative_to(ROOT)),'sha256':hashlib.sha256(q.read_bytes()).hexdigest()})
(dst/'coco_test_ids.json').write_text(json.dumps(list(spec)))
(dst/'coco_manifest.json').write_text(json.dumps({'licenses':ann['licenses'],'images':records},indent=2),encoding='utf-8')
prepare()
splits=json.loads((ROOT/'data/splits.json').read_text());assert not(set(splits['train'])&set(splits['validation']))
assert not any(int(pathlib.Path(p).stem) in spec for p in splits['train']+splits['validation'])
print('FINAL SPLITS',len(splits['train']),len(splits['validation']),len(list(dst.glob('*.png'))),flush=True)
