"""Matched VGA evidence against existing Johnson teachers, not an SOTA ranking."""
import json
from pathlib import Path
import numpy as np
from PIL import Image
import torch
from pc_validate import ROOT,metric,save_json
from teacher import load_teacher


def main():
    torch.set_num_threads(4);torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    stage=Path("C:/CodexTemp/stylecam_pc_20261004");dev="cuda" if torch.cuda.is_available() else "cpu"
    runs=["final_route_camera_temporal_fp32","final_route_camera_temporal_qat"]
    styles=["candy","mosaic","rain_princess","udnie"];results=[]
    for s in styles:
        teacher=load_teacher(str(ROOT/"data/saved_models"/f"{s}.pth"),dev)
        for f in sorted((stage/runs[0]/"images").glob("*_input.png")):
            if "proxy" in f.name:continue
            name=f.stem.removesuffix("_input");im=np.asarray(Image.open(f).convert("RGB"))
            with torch.no_grad():t=teacher(torch.from_numpy(im.copy()).permute(2,0,1)[None].float().to(dev)).clamp(0,255)
            t=t.round()[0].permute(1,2,0).byte().cpu().numpy()
            for run in runs:
                ys=[np.asarray(Image.open(stage/run/"images"/f"{name}_{s}_{mode}.png")) for mode in ("fp32","int")]
                results.append(dict(run=run,style=s,image=name,fp32_vs_teacher=metric(ys[0],t),integer_vs_teacher=metric(ys[1],t)))
        del teacher
    save_json(stage/"teacher_vga.json",dict(protocol="8 heldout images, 640x480 bilinear center fit, uint8 rounded Johnson outputs",results=results))
    for run in runs:
        for s in styles:
            a=[r for r in results if r["run"]==run and r["style"]==s]
            print(run,s,"FP32",np.mean([r["fp32_vs_teacher"]["psnr"] for r in a]),
                  "integer",np.mean([r["integer_vs_teacher"]["psnr"] for r in a]),flush=True)


if __name__=="__main__":main()
