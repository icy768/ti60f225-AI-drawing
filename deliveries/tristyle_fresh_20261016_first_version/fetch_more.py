from bootstrap import fetch
import requests,pathlib,concurrent.futures
def art(oid):
    r=requests.get(f'https://collectionapi.metmuseum.org/public/collection/v1/objects/{oid}',timeout=20);r.raise_for_status();o=r.json();pathlib.Path(f'sources/met_{oid}.json').write_text(r.text,encoding='utf-8')
    if o.get('isPublicDomain') and 'Gogh' in o.get('artistDisplayName',''):
        print(o['title'],flush=True);fetch(o['primaryImageSmall'],f'data/references/vangogh/{oid}.jpg')
with concurrent.futures.ThreadPoolExecutor(4) as ex:
    for f in ex.map(art,[436532,436534,436535,436536]):pass
fetch('https://download.blender.org/durian/trailer/sintel_trailer-480p.mp4','data/video/sintel_trailer-480p.mp4')
fetch('https://durian.blender.org/sharing/','sources/Sintel_license.html')
