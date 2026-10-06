import argparse, json, os
from pathlib import Path
import numpy as np, torch
from PIL import Image, ImageOps, ImageDraw
from tinystyle import TinyStyleNet, QCfg
from train import ROOT, VGGFeat, image_list
from train_art_styles import gram, art_tensor

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--run",default="runs/art_styles_c24_fp32")
    ap.add_argument("--W",type=int,default=640)
    ap.add_argument("--H",type=int,default=480)
    args=ap.parse_args()
    run=Path(ROOT)/args.run; ck=torch.load(run/"student.pt",map_location="cpu",weights_only=False)
    dev="cuda" if torch.cuda.is_available() else "cpu"; net=TinyStyleNet(**ck["cfg"]).to(dev).eval(); net.load_state_dict(ck["sd"]); QCfg.enabled=False; QCfg.observe=False
    vgg=VGGFeat().to(dev).eval(); names=ck["styles"]
    style_files=[Path(ROOT)/"data/styles_art/van_gogh_wheat_field.jpg",Path(ROOT)/"data/styles_art/ukiyo_e_hokusai_great_wave.jpg",Path(ROOT)/"data/styles_art/ink_ni_zan_woods_valleys.jpg"]
    with torch.no_grad(): refs=[vgg(art_tensor(p,256).to(dev)) for p in style_files]; refg=[[gram(z) for z in f] for f in refs]
    _, files=image_list(); files=files[:8]; rows=[]; stats={n:{"gram_mse_before":[],"gram_mse_after":[],"content_l1":[]} for n in names}
    for f in files:
        im=Image.open(f).convert("RGB"); im=ImageOps.fit(im,(args.W,args.H),method=Image.Resampling.BICUBIC); a=np.asarray(im)
        x=torch.from_numpy(a).permute(2,0,1).unsqueeze(0).float().to(dev)/255
        with torch.no_grad():
            fx=vgg(x)
            tile=[im]
            for si,n in enumerate(names):
                y=net(x,torch.tensor([si],device=dev)).clamp(0,1)
                fy=vgg(y)
                before=sum(float(torch.mean((gram(q)-r.expand(q.shape[0],-1,-1))**2)) for q,r in zip(fx,refg[si]))
                after=sum(float(torch.mean((gram(q)-r.expand(q.shape[0],-1,-1))**2)) for q,r in zip(fy,refg[si]))
                stats[n]["gram_mse_before"].append(before); stats[n]["gram_mse_after"].append(after)
                stats[n]["content_l1"].append(float(torch.mean(torch.abs(y-x))))
                tile.append(Image.fromarray((y[0].permute(1,2,0).cpu().numpy()*255).round().astype(np.uint8)))
        row=Image.new("RGB",(320*len(tile),240),(255,255,255))
        for i,t in enumerate(tile): row.paste(t.resize((320,240)),(i*320,0))
        rows.append(row)
    out=Image.new("RGB",(320*4,240*len(rows)),(255,255,255))
    for i,r in enumerate(rows): out.paste(r,(0,i*240))
    out.save(run/"art_styles_montage.jpg",quality=92)
    summary={"checkpoint":str(run/"student.pt"),"styles":names,"n_images":len(files),"W":args.W,"H":args.H,"metrics":{}}
    for n,s in stats.items():
        b=float(np.mean(s["gram_mse_before"])); a=float(np.mean(s["gram_mse_after"]));
        summary["metrics"][n]={"style_gram_mse_before":b,"style_gram_mse_after":a,"relative_reduction":1-a/b if b else None,"content_l1_0_1":float(np.mean(s["content_l1"]))}
    (run/"art_style_eval.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False,indent=2)); print("montage",run/"art_styles_montage.jpg")
if __name__=="__main__": main()
