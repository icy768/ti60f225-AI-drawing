"""Fetch only named public sources into this independent project; no local legacy reads."""
from pathlib import Path
import concurrent.futures as cf, requests, json, hashlib, time, zipfile
ROOT = Path(__file__).resolve().parent
SESSION = requests.Session()
SESSION.headers['User-Agent'] = 'TriStyleResearch/1.0 (public-source reproducibility)'
def fetch(url, dest, timeout=60):
    dest=ROOT/dest; dest.parent.mkdir(parents=True,exist_ok=True)
    if dest.exists() and dest.stat().st_size: return dest
    tmp=dest.with_suffix(dest.suffix+'.part')
    for attempt in range(3):
        try:
            with SESSION.get(url,stream=True,timeout=timeout) as r:
                r.raise_for_status()
                with tmp.open('wb') as f:
                    for chunk in r.iter_content(1<<20): f.write(chunk)
            tmp.replace(dest)
            record={'url':url,'file':str(dest.relative_to(ROOT)),'bytes':dest.stat().st_size,'sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'downloaded_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
            with (ROOT/'sources/downloads.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(record,ensure_ascii=False)+'\n')
            print('OK',record['file'],record['bytes'],flush=True);return dest
        except Exception as e:
            print('RETRY',url,type(e).__name__,str(e)[:120],flush=True);time.sleep(1)
    raise RuntimeError(url)
def main():
    (ROOT/'sources').mkdir(exist_ok=True)
    items=[
      ('https://efrosgans.eecs.berkeley.edu/cyclegan/pretrained_models/style_vangogh.pth','teachers/weights/cycle_vangogh.pth'),
      ('https://efrosgans.eecs.berkeley.edu/cyclegan/pretrained_models/style_ukiyoe.pth','teachers/weights/cycle_ukiyoe.pth'),
      ('https://cs.stanford.edu/people/jcjohns/fast-neural-style/models/eccv16/starry_night.t7','teachers/weights/johnson_starry_night.t7'),
      ('https://cs.stanford.edu/people/jcjohns/fast-neural-style/models/eccv16/the_wave.t7','teachers/weights/johnson_the_wave.t7'),
      ('https://raw.githubusercontent.com/junyanz/pytorch-CycleGAN-and-pix2pix/master/LICENSE','sources/CycleGAN_LICENSE.txt'),
      ('http://images.cocodataset.org/zips/val2017.zip','data/raw/val2017.zip'),
      ('https://download.pytorch.org/models/vgg16-397923af.pth','teachers/weights/vgg16.pth'),
    ]
    with cf.ThreadPoolExecutor(5) as ex:
        futures={ex.submit(fetch,u,p):p for u,p in items}
        for f in cf.as_completed(futures):
            try:f.result()
            except Exception as e:print('FAILED',futures[f],str(e),flush=True)
    z=ROOT/'data/raw/val2017.zip'
    if z.exists():
        with zipfile.ZipFile(z) as f:
            # Fixed named official COCO archive; prohibit arbitrary archive traversal.
            names=[n for n in f.namelist() if n.startswith('val2017/') and n.endswith('.jpg') and '..' not in n]
            for name in names:f.extract(name,ROOT/'data/raw')
        print('EXTRACTED',len(names),flush=True)
if __name__=='__main__': main()
