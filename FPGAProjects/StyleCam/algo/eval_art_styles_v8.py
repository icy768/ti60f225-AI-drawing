"""VGA content diagnostics, learned-target fidelity and phase stability.
Metrics are not artistic scores. Does not treat original-photo PSNR as quality.
"""
import argparse,json,hashlib
from pathlib import Path
import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image,ImageOps,ImageDraw
from train import ROOT,image_list
from tinystyle import TinyStyleNet,QCfg
from eval_art_styles_v4 import statistics,tensor
from art_structure_v8 import target,separated_loss

def main():
    p=argparse.ArgumentParser();p.add_argument('--models',nargs='+',required=True);p.add_argument('--out',required=True)
    p.add_argument('--count',type=int,default=24);p.add_argument('--save_count',type=int,default=8)
    args=p.parse_args();root=Path(ROOT);out=root/args.out;out.mkdir(parents=True,exist_ok=False)
    torch.set_num_threads(4);QCfg.enabled=QCfg.observe=False
    train,held=image_list();files=held[:args.count];assert not set(files)&set(train)
    report={'development_set':True,'size':[640,480],'real_camera_video':False,'board_fps':None,'models':{}}
    for cp in args.models:
        path=root/cp;ck=torch.load(path,map_location='cpu',weights_only=False);name=path.parent.name
        n=TinyStyleNet(**ck['cfg']).cuda().eval();n.load_state_dict(ck['sd']);dest=out/name;dest.mkdir()
        records=[]
        with torch.no_grad():
            for j,f in enumerate(files):
                im=ImageOps.fit(ImageOps.exif_transpose(Image.open(f)).convert('RGB'),(640,480),Image.Resampling.BILINEAR)
                x=tensor(im,'cuda');rec={'image':Path(f).name,'styles':{}}
                if j<args.save_count:im.save(dest/f'{j:03}_input.png')
                for si,style in enumerate(ck['styles']):
                    st=torch.tensor([si],device='cuda');y=n(x,st)
                    rgb=(y[0].permute(1,2,0).cpu().numpy()*255).round().astype(np.uint8);stat=statistics(rgb)
                    if si:
                        t=target(x,si);pix,grad,tone=separated_loss(y,t)
                        stat.update(target_region_mae=float(pix),target_signed_gradient_mae=float(grad),target_dark_paper_mae=float(tone))
                    if j<12:
                        for dy,dx in [(2,1),(4,4)]:
                            m=32;p0=12;sx=F.pad(x,(p0,)*4,mode='reflect')[:,:,p0+dy:p0+dy+480,p0+dx:p0+dx+640]
                            sy=n(sx,st)
                            stat[f'shift_{dy}_{dx}_mae_255']=float(F.l1_loss(sy[:,:,m:-m,m:-m],y[:,:,m+dy:480-m+dy,m+dx:640-m+dx])*255)
                    rec['styles'][style]=stat
                    if j<args.save_count:Image.fromarray(rgb).save(dest/f'{j:03}_{style}.png')
                records.append(rec)
                if (j+1)%50==0:print(name,j+1,flush=True)
        means={s:{k:float(np.mean([r['styles'][s][k] for r in records if k in r['styles'][s]])) for k in records[0]['styles'][s]} for s in ck['styles']}
        report['models'][name]={'path':cp,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'means':means,'records':records}
        (out/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'name':name,'means':means}),flush=True)
    names=list(report['models']);styles=['van_gogh','ukiyo_e','ink_landscape']
    for j in range(args.save_count):
        sheet=Image.new('RGB',(320*(len(names)+1),268*3),'white');d=ImageDraw.Draw(sheet)
        for r,s in enumerate(styles):
            paths=[out/names[0]/f'{j:03}_input.png']+[out/n/f'{j:03}_{s}.png' for n in names]
            for c,path in enumerate(paths):
                im=Image.open(path);sheet.paste(im.resize((320,240)),(c*320,r*268+28))
                d.text((c*320+4,r*268+5),(['Input']+names)[c]+' / '+s,fill='black')
        sheet.save(out/f'comparison_{j:03}.jpg',quality=95)

if __name__=='__main__':main()
