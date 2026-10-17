"""Restore ONLY frozen manifest members with exact hashes; never adopt new training images."""
import argparse,base64,hashlib,json,pathlib,requests,concurrent.futures,zipfile,sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser();ap.add_argument('--photos',action='store_true');ap.add_argument('--references',action='store_true')
ap.add_argument('--training-teachers',action='store_true');ap.add_argument('--video',action='store_true');ap.add_argument('--annotations',action='store_true');a=ap.parse_args()
meta=json.loads((ROOT/'data/USED_DATA_manifest.json').read_text(encoding='utf-8'));items=[]
if a.annotations:
    row=meta['annotation'];items.append((row['source_zip'],row['file'],row['sha256']))
if a.photos:
    for row in meta['COCO_used']:items.append((row['coco']['coco_url'],row['file'],row['sha256']))
if a.references:
    for row in meta['art_references']:
        url=row.get('primaryImage') or row.get('source_url')
        if not url:raise ValueError('Exact source missing:'+row['file'])
        items.append((url,row['file'],row['sha256']))
if a.video:
    row=meta['video'];items.append((row['source'],row['file'],row['sha256']))
if a.training_teachers:
    allowed={'teachers/weights/vgg16.pth','teachers/weights/adain_vgg.pth','teachers/weights/adain_decoder.pth','teachers/weights/depth_anything_v2_vits.pth'}
    for f in ('downloads.jsonl','depth_v2_downloads.jsonl'):
        for line in (ROOT/'sources'/f).read_text(encoding='utf-8').splitlines():
            row=json.loads(line);path=row.get('file',row.get('path','')).replace('\\','/')
            if path in allowed:items.append((row['url'],path,row['sha256']))
    found={i[1].replace('\\','/') for i in items};assert allowed<=found,'Missing recorded required teacher URL'
assert items,'Choose --photos/--references/--training-teachers/--video/--annotations'
def fetch(item):
    url,rel,expected=item;p=(ROOT/pathlib.Path(rel.replace('\\','/'))).resolve()
    assert p.is_relative_to(ROOT),'Out of project path'
    if p.exists():
        assert hashlib.sha256(p.read_bytes()).hexdigest()==expected,f'Existing file mismatches; preserve and investigate: {p}'
        return
    p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix(p.suffix+'.fetchpart')
    if rel.replace('\\','/')=='data/raw/instances_val2017.json':
        sys.path.insert(0,str(ROOT))
        from fetch_coco_subset import RemoteZip,member
        row=meta['annotation'];z=zipfile.ZipFile(RemoteZip(url,row['archive_bytes']))
        tmp.write_bytes(member(url,row['archive_bytes'],z.getinfo(row['member'])))
    elif '/git/blobs/' in url:
        r=requests.get(url,timeout=60);r.raise_for_status();raw=base64.b64decode(r.json()['content']);tmp.write_bytes(raw)
    else:
        with requests.get(url,stream=True,timeout=(15,120)) as r:
            r.raise_for_status()
            with tmp.open('wb') as f:
                for chunk in r.iter_content(1024*1024):f.write(chunk)
    assert hashlib.sha256(tmp.read_bytes()).hexdigest()==expected,f'Download hash mismatch:{url}'
    tmp.replace(p)
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    for n,_ in enumerate(pool.map(fetch,items),1):
        if n%50==0:print('VERIFIED',n,'/',len(items),flush=True)
print('RESTORED_AND_HASH_VERIFIED',len(items))
