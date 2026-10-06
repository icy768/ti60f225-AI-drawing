"""Comparable fixed-VGA diagnostics and synthetic translation checks."""
import argparse,hashlib,json
from pathlib import Path
import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image,ImageOps,ImageDraw
from tinystyle import TinyStyleNet,QCfg
from train import ROOT,image_list
from eval_art_styles_v4 import statistics,tensor
from train_art_styles_v4 import ArtFeatures,reference_bank,NAMES
from train_art_styles import gram
from art_material_v7 import PatchBank,material_target


def image_tensor(path):
    im=ImageOps.fit(ImageOps.exif_transpose(Image.open(path)).convert('RGB'),(640,480),Image.Resampling.BILINEAR)
    return im,tensor(im,'cuda')


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--checkpoints',nargs='+',required=True)
    ap.add_argument('--out',required=True);ap.add_argument('--count',type=int,default=24)
    ap.add_argument('--shift_count',type=int,default=12);ap.add_argument('--save_count',type=int,default=8)
    args=ap.parse_args();torch.set_num_threads(4);root=Path(ROOT);out=root/args.out
    out.mkdir(parents=True,exist_ok=False);QCfg.enabled=QCfg.observe=False
    vgg=ArtFeatures().cuda().eval();refs=reference_bank(out,'cuda',256,coarse_brush=True)
    with torch.no_grad():
        targets=[]
        for local in refs:
            features=[vgg(x) for x,w in local]
            gs=[sum(w*gram(f[i]) for f,(_,w) in zip(features,local)) for i in range(4)]
            targets.append((gs,PatchBank(features)))
    train,held=image_list();files=held[:args.count];assert not set(files)&set(train)
    report={'size':[640,480],'development_set':True,'no_board_fps_claim':True,'models':{}}
    for checkpoint in args.checkpoints:
        path=root/checkpoint;name=path.parent.name+'_'+path.stem
        dest=out/name;dest.mkdir()
        ck=torch.load(path,map_location='cpu',weights_only=False)
        net=TinyStyleNet(**ck['cfg']).cuda().eval();net.load_state_dict(ck['sd'])
        rows=[];records=[]
        with torch.no_grad():
            for j,file in enumerate(files):
                im,x=image_tensor(file);fx=vgg(F.interpolate(x,(256,256),mode='bilinear',align_corners=False));row=[im]
                rec={'image':Path(file).name,'styles':{}}
                for si,sty in enumerate(ck['styles']):
                    st=torch.tensor([si],device='cuda');y=net(x,st).clamp(0,1)
                    rgb=(y[0].permute(1,2,0).cpu().numpy()*255).round().astype(np.uint8)
                    yi=Image.fromarray(rgb);row.append(yi)
                    stat=statistics(rgb)
                    fy=vgg(F.interpolate(y,(256,256),mode='bilinear',align_corners=False));gs,bank=targets[NAMES.index(sty)]
                    stat['content_relative_mse']=float(F.mse_loss(fy[2],fx[2])/fx[2].square().mean().clamp_min(1e-6))
                    stat['reference_relative_gram']=float(sum(F.mse_loss(gram(f),g)/g.square().mean().clamp_min(1e-8) for f,g in zip(fy,gs))/4)
                    stat['reference_patch_mse']=float(bank.loss(fy[1]))
                    if j<args.shift_count:
                        for dy,dx in [(2,1),(4,4)]:
                            p=12;m=32
                            sx=F.pad(x,(p,)*4,mode='reflect')[:,:,p+dy:p+dy+480,p+dx:p+dx+640]
                            sy=net(sx,st)
                            stat[f'shift_{dy}_{dx}_mae_255']=float(F.l1_loss(sy[:,:,m:-m,m:-m],y[:,:,m+dy:480-m+dy,m+dx:640-m+dx])*255)
                    rec['styles'][sty]=stat
                    if j<args.save_count:yi.save(dest/f'{j:03}_{sty}.png')
                if j<args.save_count:
                    im.save(dest/f'{j:03}_input.png');rows.append(row)
                records.append(rec)
                if (j+1)%25==0:print(name,j+1,'/',len(files),flush=True)
        means={s:{k:float(np.mean([r['styles'][s][k] for r in records if k in r['styles'][s]])) for k in records[0]['styles'][s]} for s in ck['styles']}
        report['models'][name]={'checkpoint':checkpoint,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'means':means,'records':records}
        for start in range(0,len(rows),4):
            group=rows[start:start+4];sheet=Image.new('RGB',(320*(1+len(ck['styles'])),268*len(group)),'white');d=ImageDraw.Draw(sheet)
            for r,row in enumerate(group):
                for c,im in enumerate(row):
                    d.text((c*320+5,r*268+7),(['Input']+ck['styles'])[c],fill='black')
                    sheet.paste(im.resize((320,240),Image.Resampling.LANCZOS),(c*320,r*268+28))
            sheet.save(dest/f'comparison_{start//4+1:02}.jpg',quality=95)
        print(json.dumps({'model':name,'means':means}),flush=True)
        (out/'summary.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
        del net
    # Original | baseline | candidate for each style, same content frame.
    model_names=list(report['models'])
    if len(model_names)>=2:
        for j in range(min(args.save_count,4)):
            a=out/model_names[0];b=out/model_names[-1]
            sheet=Image.new('RGB',(960,804),'white');d=ImageDraw.Draw(sheet)
            for r,sty in enumerate(['van_gogh','ukiyo_e','ink_landscape']):
                paths=[a/f'{j:03}_input.png',a/f'{j:03}_{sty}.png',b/f'{j:03}_{sty}.png']
                for c,p in enumerate(paths):
                    d.text((c*320+5,r*268+7),['Input',model_names[0],model_names[-1]][c]+' / '+sty,fill='black')
                    sheet.paste(Image.open(p).resize((320,240)),(c*320,r*268+28))
            sheet.save(out/f'compare_models_{j:03}.jpg',quality=95)


if __name__=='__main__':main()
