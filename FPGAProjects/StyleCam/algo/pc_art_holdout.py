"""Additional held-out images not used for visual tuning in this turn."""
import json
from pathlib import Path
import numpy as np
import torch
from PIL import Image
import golden
from pc_validate import ROOT,read_rgb,metric,save_json,make_montage
from train import image_list,VGGFeat
from train_art_styles import art_tensor,gram
from tinystyle import TinyStyleNet,QCfg


def main():
    torch.set_num_threads(4);QCfg.enabled=False;QCfg.observe=False
    stage=Path("C:/CodexTemp/stylecam_pc_20261004");wd=stage/"art_styles_c24_hwqat";out=wd/"holdout";out.mkdir(exist_ok=True)
    q0=golden.load(str(stage/"art_styles_c24_strong/qparams"));q1=golden.load(str(wd/"qparams"))
    ck=torch.load(ROOT/"runs/art_styles_c24_strong/student.pt",map_location="cpu",weights_only=False)
    dev="cuda" if torch.cuda.is_available() else "cpu"
    net=TinyStyleNet(**ck["cfg"]).to(dev).eval();net.load_state_dict(ck["sd"])
    vgg=VGGFeat().to(dev).eval();sources=json.loads((ROOT/"data/styles_art/provenance.json").read_text())
    with torch.no_grad():refs=[[gram(z) for z in vgg(art_tensor(ROOT/"data/styles_art"/s["file"]).to(dev))] for s in sources]
    _,files=image_list();files=files[80:96];results=[];views=[]
    for i,f in enumerate(files):
        im=read_rgb(f);row=[im]
        x=torch.from_numpy(im.copy()).permute(2,0,1)[None].float().to(dev)/255
        with torch.no_grad():fx=vgg(x)
        for s,name in enumerate(q1["styles"]):
            before=sum(float((gram(z)-t).square().mean()) for z,t in zip(fx,refs[s]))
            with torch.no_grad():fp=net(x,torch.tensor([s],device=dev)).clamp(0,1)
            fp=(fp[0].permute(1,2,0).cpu().numpy()*255).round().astype(np.uint8)
            y0,_,_=golden.run(q0,im,s);y1,_,_=golden.run(q1,im,s)
            with torch.no_grad():fy=vgg(torch.from_numpy(y1.copy()).permute(2,0,1)[None].float().to(dev)/255)
            dist=[sum(float((gram(z)-t).square().mean()) for z,t in zip(fy,ref)) for ref in refs]
            results.append(dict(image=Path(f).stem,style=name,ptq_vs_float=metric(y0,fp),hwqat_vs_float=metric(y1,fp),
                                gram_input_to_target=before,gram_hwqat_to_target=dist[s],all_style_distances=dist))
            row.append(y1)
            if i<4:Image.fromarray(y1).save(out/f"{Path(f).stem}_{name}.png")
        if i<4:views.append(row)
        print("HOLDOUT",i+1,Path(f).name,flush=True)
    make_montage(views,["Input"]+q1["styles"],out/"unseen_integer_styles.jpg")
    summary={}
    for s,name in enumerate(q1["styles"]):
        a=[r for r in results if r["style"]==name]
        summary[name]={"ptq_psnr":float(np.mean([r["ptq_vs_float"]["psnr"] for r in a])),
                       "hwqat_psnr":float(np.mean([r["hwqat_vs_float"]["psnr"] for r in a])),
                       "hwqat_ssim":float(np.mean([r["hwqat_vs_float"]["ssim"] for r in a])),
                       "gram_reduction":1-float(np.mean([r["gram_hwqat_to_target"] for r in a]))/float(np.mean([r["gram_input_to_target"] for r in a])),
                       "nearest_reference_count":sum(int(np.argmin(r["all_style_distances"])==s) for r in a)}
    save_json(out/"holdout.json",dict(protocol="COCO evaluation split indices 80:96; VGA bilinear center fit; FP target is strong FP32 art model; not industry SOTA or human style recognition",n=16,summary=summary,results=results))
    print(json.dumps(summary,indent=2),flush=True)


if __name__=="__main__":main()
