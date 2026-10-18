"""Native saved inference comparison; not an artistic scoring function."""
import argparse
import hashlib
import html
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
STYLES = ('vangogh', 'ukiyoe', 'ink')


def panel(images, labels, title, crop=False):
    w,h = (256,256) if crop else (384,288)
    canvas = Image.new('RGB', (w*len(images),h+42), 'white'); draw = ImageDraw.Draw(canvas)
    for i,(im,label) in enumerate(zip(images,labels)):
        im = im.copy()
        if crop:
            cx,cy=im.width//2,im.height//2
            im=im.crop((cx-128,cy-128,cx+128,cy+128))
        else: im.thumbnail((w,h),Image.Resampling.LANCZOS)
        canvas.paste(im,(i*w,0)); draw.text((i*w+3,h+2),label,fill='black')
    draw.text((3,h+23),title,fill='black')
    return canvas


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--run',required=True); ap.add_argument('--step',type=int,required=True)
    args=ap.parse_args(); folder=ROOT/'reports'/args.run/f'{args.step:06d}'
    out=folder/'review'; out.mkdir(exist_ok=True)
    inputs=json.loads((ROOT/'data/fixed_test_manifest.json').read_text())
    body=['<!doctype html><meta charset="utf-8"><title>V4 actual student comparison</title>',
          '<style>body{font:16px sans-serif;max-width:1400px;margin:auto}img{max-width:100%}section{margin:2em 0}</style>',
          f'<h1>{html.escape(args.run)} step {args.step}</h1>',
          '<p>Actual saved student outputs. Fixed17 is a repeatedly reviewed diagnostic set, not a blind test. No artistic promotion from loss or software statistics.</p>']
    rows=[]; stems=[]
    for filename,entry in inputs.items():
        stem=Path(filename).stem; stems.append(stem); p=Path(entry['path'])
        assert hashlib.sha256(p.read_bytes()).hexdigest()==entry['sha256']
        x=Image.open(p).convert('RGB')
        for style in STYLES:
            v3=Image.open(folder/f'{stem}_{style}_V3.png').convert('RGB')
            y=Image.open(folder/f'{stem}_{style}_V4pilot.png').convert('RGB')
            assert x.size==v3.size==y.size
            ims=[x,v3,y]; labels=['INPUT','V3 frozen',args.run]
            panel(ims,labels,f'{stem} / {style}').save(out/f'{stem}_{style}_full.jpg',quality=95)
            panel(ims,labels,f'{stem} / {style} native center',True).save(out/f'{stem}_{style}_crop.png')
            a,b=np.array(x)/255.,np.array(y)/255.
            rows.append({'scene':stem,'style':style,'size':list(y.size),'input_MAE':float(np.abs(a-b).mean()),
                         'output_sha256':hashlib.sha256((folder/f'{stem}_{style}_V4pilot.png').read_bytes()).hexdigest()})
            body.append(f'<section><h2>{stem} / {style}</h2><img loading="lazy" src="{stem}_{style}_full.jpg"><p><a href="{stem}_{style}_crop.png">Native center crop</a> | <a href="../{stem}_{style}_V4pilot.png">Full native candidate</a> | <a href="../{stem}_{style}_V3.png">Full native V3</a></p></section>')
    for style in STYLES:
        for start in range(0,len(stems),6):
            group=stems[start:start+6]; page=Image.new('RGB',(1152,330*len(group)),'white')
            for row,stem in enumerate(group): page.paste(Image.open(out/f'{stem}_{style}_full.jpg'),(0,330*row))
            page.save(out/f'{style}_overview_{start//6+1}.jpg',quality=94)
    ck=ROOT/'experiments'/args.run/f'step_{args.step:06d}.pt'
    (out/'measurements.json').write_text(json.dumps({'kind':'size/hash/change diagnostics, NOT artistic score',
        'checkpoint_sha256':hashlib.sha256(ck.read_bytes()).hexdigest(),'rows':rows,'promoted':False},indent=2))
    (out/'INDEX.html').write_text('\n'.join(body),encoding='utf-8')
    print(json.dumps({'run':args.run,'step':args.step,'scene_count':len(stems),'output_count':len(rows),'review':str(out/'INDEX.html')}))


if __name__=='__main__':main()
