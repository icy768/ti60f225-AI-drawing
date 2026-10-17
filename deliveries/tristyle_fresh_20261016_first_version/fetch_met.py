"""Use only museum objects explicitly marked public domain."""
import requests, pathlib, json
from bootstrap import fetch
for style,query,limit in [('ink','Shitao',8),('ink','Shen Zhou landscape',6),('vangogh','Vincent van Gogh',6),('ukiyoe','Hokusai Fuji',8)]:
    r=requests.get('https://collectionapi.metmuseum.org/public/collection/v1.1/search',params={'hasImages':'true','q':query,'limit':limit},timeout=25);r.raise_for_status()
    for oid in r.json().get('objectIDs',[]):
        try:
            r=requests.get(f'https://collectionapi.metmuseum.org/public/collection/v1/objects/{oid}',timeout=25);r.raise_for_status();o=r.json()
            pathlib.Path(f'sources/met_{oid}.json').write_text(r.text,encoding='utf-8')
            if not o.get('isPublicDomain') or not o.get('primaryImageSmall'):continue
            print(style,oid,o['title'],o.get('artistDisplayName'),flush=True)
            fetch(o['primaryImageSmall'],f'data/references/{style}/{oid}.jpg')
        except Exception as e:print('SKIP',oid,str(e)[:150],flush=True)
