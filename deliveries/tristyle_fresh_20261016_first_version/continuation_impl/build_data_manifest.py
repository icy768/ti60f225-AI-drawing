"""Audit only originals actually used in this new project; never add images to training."""
import hashlib,json,pathlib
ROOT=pathlib.Path(__file__).resolve().parents[1]
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
splits=json.loads((ROOT/'data/splits.json').read_text());ann=json.loads((ROOT/'data/raw/instances_val2017.json').read_text())
images={r['id']:r for r in ann['images']};licenses={r['id']:r for r in ann['licenses']}
test_ids=set(json.loads((ROOT/'data/test/coco_test_ids.json').read_text()));photos=[]
assert not set(splits['train'])&set(splits['validation'])
for split in ('train','validation'):
    for rel in splits[split]:
        p=ROOT/rel;r=images[int(p.stem)];assert r['license'] in (4,5,8) and r['id'] not in test_ids
        photos.append({'split':split,'file':rel,'sha256':digest(p),'coco':r,'license':licenses[r['license']]})
testmeta={}
for name in ('manifest.json','coco_manifest.json'):
    p=ROOT/'data/test'/name
    if p.exists():testmeta[name]=json.loads(p.read_text())
tests=[{'file':str(p.relative_to(ROOT)),'size_bytes':p.stat().st_size,'sha256':digest(p)} for p in sorted((ROOT/'data/test').glob('*.png'))]
art=[]
for p in sorted((ROOT/'data/references').rglob('*.jpg')):
    meta=ROOT/'sources'/('met_'+p.stem+'.json');row={'file':str(p.relative_to(ROOT)),'sha256':digest(p)}
    if meta.exists():
        r=json.loads(meta.read_text(encoding='utf-8'));row.update({k:r.get(k) for k in ('objectID','title','artistDisplayName','objectDate','isPublicDomain','objectURL','primaryImage')})
        assert r.get('isPublicDomain') is True
    elif p.name=='starry_night.jpg':
        tree=json.loads((ROOT/'sources/fast-neural-style_tree.json').read_text())
        item=next(t for t in tree['tree'] if t['path']=='images/styles/starry_night.jpg')
        raw=p.read_bytes();gitsha=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
        assert gitsha==item['sha']
        row.update({'source':'Historical Van Gogh artwork; bytes verified equal to the official Johnson repository Git blob. Original fetch timestamp not reconstructed.',
            'source_url':item['url'],'git_blob_sha1':gitsha,'official_path':item['path']})
    else:row['source']='Historical artwork; exact original fetch provenance not reconstructed; no invented Met PD assertion.'
    art.append(row)
video=ROOT/'data/video/sintel_trailer-480p.mp4';pairs=json.loads((ROOT/'data/video/train_pairs/manifest.json').read_text())
res={'status':'MEASURED files/hashes, original attribution metadata preserved','counts':{k:len(splits[k]) for k in ('train','validation')},
    'annotation':{'file':'data/raw/instances_val2017.json','sha256':digest(ROOT/'data/raw/instances_val2017.json'),
        'source_zip':'http://images.cocodataset.org/annotations/annotations_trainval2017.zip','archive_bytes':252907541,'member':'annotations/instances_val2017.json'},
    'optimizer_excludes_fixed_test_IDs':True,'COCO_used':photos,'fixed_test_files':tests,'fixed_test_source_metadata':testmeta,
    'art_references':art,'video':{'file':str(video.relative_to(ROOT)),'sha256':digest(video),'source':'https://download.blender.org/durian/trailer/sintel_trailer-480p.mp4',
        'attribution':'Sintel, Blender Foundation, CC BY3.0; model-processed derivative clips are labeled. Animated source film, not camera/board footage.',
        'train_pair_first_frame_max':max(r['frame'] for r in pairs['pairs']),'train_pair_second_frame_max':max(r['frame'] for r in pairs['pairs'])+1,
        'action_test_start':640,'action_test_end':789,'fps':pairs['fps']}}
(ROOT/'data/USED_DATA_manifest.json').write_text(json.dumps(res,indent=1,ensure_ascii=False),encoding='utf-8')
print('AUDIT_OK',res['counts'],'test',len(tests),'art',len(art))
