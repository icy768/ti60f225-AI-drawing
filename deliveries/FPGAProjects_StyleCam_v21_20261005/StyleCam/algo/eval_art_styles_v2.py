"""Generate visual and quantitative evidence for the v2 float art checkpoint."""
from pathlib import Path
import json, math
import numpy as np
import torch
from PIL import Image, ImageDraw
from tinystyle import TinyStyleNet, QCfg
from train import ROOT, image_list, VGGFeat
from train_art_styles import gram, art_tensor

def read(path): return np.asarray(Image.open(path).convert("RGB"),dtype=np.uint8)
def tensor(im,dev): return torch.from_numpy(im.copy()).permute(2,0,1)[None].float().to(dev)/255
def save_montage(rows, labels, path):
    H,W=rows[0][0].shape[:2]; cellw=W; cellh=H+24
    out=Image.new("RGB",(cellw*len(labels),cellh*len(rows)),"white"); d=ImageDraw.Draw(out)
    for i,row in enumerate(rows):
        for j,(im,label) in enumerate(zip(row,labels)):
            out.paste(Image.fromarray(im),(j*cellw,i*cellh+24)); d.text((j*cellw+4,i*cellh+4),label,fill="black")
    out.save(path,quality=94)
def main():
    root=Path(ROOT); out=root/"runs/art_styles_c24_strong_v2"; ev=out/"evaluation"; ev.mkdir(exist_ok=True)
    ck=torch.load(out/"student.pt",map_location="cpu",weights_only=False); dev="cuda" if torch.cuda.is_available() else "cpu"
    net=TinyStyleNet(**ck["cfg"]).to(dev).eval(); net.load_state_dict(ck["sd"]); QCfg.enabled=False; QCfg.observe=False
    _,files=image_list(); files=files[::max(1,len(files)//8)][:8]
    labels=["Input","Van Gogh","Ukiyo-e","Ink wash"]; rows=[]; stats=[]
    with torch.no_grad():
        for f in files:
            im=read(f); x=tensor(im,dev); row=[im]
            outs=[]
            for s in range(3):
                y=net(x,torch.tensor([s],device=dev)).clamp(0,1)[0].permute(1,2,0).cpu().numpy()
                yi=np.clip(np.round(y*255),0,255).astype(np.uint8); row.append(yi); outs.append(yi)
            rows.append(row)
            stats.append({"image":Path(f).name,"input_sat":float((im.max(2)-im.min(2)).mean()),"style_sat":[float((z.max(2)-z.min(2)).mean()) for z in outs],"gray_mean":[float((0.299*z[:,:,0]+0.587*z[:,:,1]+0.114*z[:,:,2]).mean()) for z in outs],"edge_proxy":[float(np.abs(np.diff(z.astype(np.float32),axis=0)).mean()+np.abs(np.diff(z.astype(np.float32),axis=1)).mean()) for z in outs]})
            for s,yi in enumerate(outs): Image.fromarray(yi).save(ev/f"{Path(f).stem}_{labels[s+1].lower().replace('-','_').replace(' ','_')}.png")
    save_montage(rows,labels,ev/"unseen_float_strong_v2.jpg")
    summary={"checkpoint":str(out/"student.pt"),"n":len(rows),"mean_input_sat":float(np.mean([r['input_sat'] for r in stats])),"mean_style_sat":[float(np.mean([r['style_sat'][s] for r in stats])) for s in range(3)],"mean_gray":[float(np.mean([r['gray_mean'][s] for r in stats])) for s in range(3)],"mean_edge_proxy":[float(np.mean([r['edge_proxy'][s] for r in stats])) for s in range(3)],"stats":stats,"note":"Float outputs on image_list evaluation split; style statistics are diagnostics, not human style scores."}
    (ev/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8"); print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=="__main__": main()
