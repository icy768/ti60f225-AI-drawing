import requests,pathlib,json,concurrent.futures
from bootstrap import fetch
p=pathlib.Path('sources')
for style,query,n in [('vangogh','Vincent van Gogh',6),('ukiyoe','Hokusai landscape',6),('ink','Shitao landscape',6)]:
    r=requests.get('https://api.artic.edu/api/v1/artworks/search',params={'q':query,'fields':'id,title,image_id,is_public_domain,artist_title','limit':20},timeout=20)
    (p/(style+'_artic.json')).write_text(r.text,encoding='utf-8')
    rows=[x for x in r.json().get('data',[]) if x.get('is_public_domain') and x.get('image_id')]
    print(style,rows[:n],flush=True)
    with concurrent.futures.ThreadPoolExecutor(4) as ex:
        for f in ex.map(lambda x:fetch(f"https://www.artic.edu/iiif/2/{x['image_id']}/full/843,/0/default.jpg",f"data/references/{style}/{x['id']}.jpg"),rows[:n]):pass
