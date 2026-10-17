import pathlib,json,hashlib,zipfile,random
from PIL import Image,ImageDraw
import numpy as np
ROOT=pathlib.Path(__file__).resolve().parent
def save_gallery(files,dest,labels=None,size=(256,192),columns=4):
    w,h=size;canvas=Image.new('RGB',(w*columns,(h+28)*((len(files)+columns-1)//columns)),(245,245,242));d=ImageDraw.Draw(canvas)
    for i,p in enumerate(files):
        im=Image.open(p).convert('RGB');im.thumbnail(size)
        x=(i%columns)*w;y=(i//columns)*(h+28)
        canvas.paste(im,(x+(w-im.width)//2,y));d.text((x+4,y+h+4),labels[i] if labels else pathlib.Path(p).stem,fill=(0,0,0))
    pathlib.Path(dest).parent.mkdir(parents=True,exist_ok=True);canvas.save(dest)
def main():
    from skimage import data
    dst=ROOT/'data/test';dst.mkdir(parents=True,exist_ok=True)
    # Original public sample photos, no outputs or files of any previous model.
    names={'sky':data.rocket,'plants':data.grass,'architecture':data.stereo_motorcycle,'water':data.eagle,'person':data.astronaut,'indoor':data.coffee,'edges':data.camera}
    rows=[]
    for name,fn in names.items():
        try:
            a=fn();a=a[0] if isinstance(a,tuple) else a
            if a.ndim==2:a=np.repeat(a[:,:,None],3,axis=2)
            im=Image.fromarray(a).convert('RGB');im.thumbnail((960,720));p=dst/(name+'.png');im.save(p)
            rows.append({'name':name,'source':'skimage.data.'+fn.__name__,'file':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'note':'Scene labels require visual confirmation; water/eagle not guaranteed water scene.'})
        except Exception as e:print('test sample unavailable',name,str(e),flush=True)
    (dst/'manifest.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
    save_gallery(list(dst.glob('*.png')),ROOT/'reports/test_inputs.jpg')
    z=ROOT/'data/raw/val2017.zip'
    if z.exists() and not (ROOT/'data/raw/val2017').exists():
        with zipfile.ZipFile(z) as f:
            for n in f.namelist():
                if n.startswith('val2017/') and n.endswith('.jpg') and '..' not in n:f.extract(n,ROOT/'data/raw')
    photos=sorted((ROOT/'data/raw/val2017').glob('*.jpg'))
    annpath=ROOT/'data/raw/instances_val2017.json'
    testmeta=ROOT/'data/test/coco_test_ids.json'
    excluded=set(json.loads(testmeta.read_text())) if testmeta.exists() else set()
    if annpath.exists():
        meta=json.loads(annpath.read_text());allowed={o['id'] for o in meta['images'] if o['license'] in [4,5,8]}
        photos=[p for p in photos if int(p.stem) in allowed and int(p.stem) not in excluded]
    # Stable membership when additional permitted originals finish downloading.
    isval=lambda p:int(hashlib.sha256(('20261016:'+p.stem).encode()).hexdigest()[:8],16)%100<8
    splits={'train':[str(p.relative_to(ROOT)) for p in photos if not isval(p)],'validation':[str(p.relative_to(ROOT)) for p in photos if isval(p)],'seed':20261016,'test':'data/test; never used in optimizer','split_rule':'SHA256(20261016:<12-digit-id>) first 32 bits mod 100 < 8 for validation'}
    (ROOT/'data/splits.json').write_text(json.dumps(splits,indent=2),encoding='utf-8')
    print('DATA',len(rows),len(splits['train']),len(splits['validation']),flush=True)
if __name__=='__main__':main()
