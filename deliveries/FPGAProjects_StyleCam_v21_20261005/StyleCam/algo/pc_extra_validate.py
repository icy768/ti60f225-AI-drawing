"""Full VGA compiled simulation, serialized banks, artwork metrics and proxy photo."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image, ImageOps
import torch

import gen_rtl
import golden
from pc_validate import ROOT, read_rgb, rtl_case, refresh_check, save_json, metric, make_montage
from tinystyle import TinyStyleNet, QCfg
from train import image_list, VGGFeat
from train_art_styles import art_tensor, gram

STAGE=Path("C:/CodexTemp/stylecam_pc_20261004")


def simulate_verilator(outdir):
    wd=Path(outdir).resolve()
    tools=Path(os.environ.get("STYLECAM_VERILATOR_ROOT", "C:/CodexTemp/verilator_py548"))
    compiler=Path(os.environ.get("STYLECAM_COMPILER_BIN", "C:/mingw64/bin"))
    env=dict(os.environ,VERILATOR_ROOT=str(tools).replace("\\","/"),
             PATH=str(compiler)+os.pathsep+"C:/Program Files/Git/usr/bin"+os.pathsep+os.environ["PATH"])
    src=["tb_top.v","stylenet_top.v"]+[str(Path(gen_rtl.RTL)/s) for s in ("common.v","swg3.v","swg3b.v","mac.v","requant.v","conv_layer.v")]
    commands=[([str(tools/"bin/verilator_bin.exe"),"--cc","--timing","--main","--exe","--top-module","tb_top",
                "--Mdir","obj_vlt","--compiler","gcc","-Wno-fatal"]+src,"verilate.log"),
              ([str(compiler/"mingw32-make.exe"),"-C","obj_vlt","-f","Vtb_top.mk","-j","4","CXX=g++","LINK=g++",
                "AR=ar","PYTHON3="+sys.executable,"CFG_CXXFLAGS_STD=-std=c++20",
                "CFG_CXXFLAGS_COROUTINES=-fcoroutines","CFG_CXXFLAGS_PCH_I=-include"],"compile.log"),
              ([str(wd/"obj_vlt/Vtb_top.exe")],"simulation.log")]
    for cmd,log in commands:
        r=subprocess.run(cmd,cwd=wd,env=env,capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=300)
        (wd/log).write_text(r.stdout+r.stderr,encoding="utf-8")
        assert r.returncode==0,(log,r.stdout[-2000:]+r.stderr[-2000:])
    assert "DONE cycles=" in r.stdout and "TIMEOUT" not in r.stdout,r.stdout
    return (r.stdout+r.stderr).splitlines()


def initial_banks(q,wd):
    out=[]
    for i,L in enumerate(q["layers"]):
        h=[int(x,16) for x in (wd/f"c{i}_{L['name']}.mem").read_text().splitlines()]
        z=np.array([h[j]|(h[j+1]<<19) for j in range(0,len(h),2)],np.int64).reshape(2*len(q["styles"]),L["cout"])
        m=(z>>20)&262143;b=z&1048575
        out.append((np.where(m&131072,m-262144,m),np.where(b&524288,b-1048576,b)))
    return out


def main():
    ap=argparse.ArgumentParser();ap.add_argument("--run",required=True);ap.add_argument("--art",action="store_true");a=ap.parse_args()
    torch.set_num_threads(4);QCfg.enabled=False;QCfg.observe=False
    wd=STAGE/Path(a.run).name;ext=wd/"extra";ext.mkdir(exist_ok=True)
    q=golden.load(str(wd/"qparams"));ck=torch.load(ROOT/a.run/"student.pt",map_location="cpu",weights_only=False)
    net=TinyStyleNet(**ck["cfg"]).eval();net.load_state_dict(ck["sd"])
    _,files=image_list();img=read_rgb(files[0])
    gen_rtl.RTL=str(STAGE/"rtl");gen_rtl.simulate=simulate_verilator;os.environ["STYLECAM_SIMULATOR"]="verilator-python 5.48.0"
    results={"run":a.run,"rtl":[],"photo":[]}
    for s in range(len(q["styles"]) if a.art else 1):
        case=ext/f"rtl_vga_{s}"
        if (case/"result.json").exists():r=json.loads((case/"result.json").read_text())
        else:r=rtl_case(q,img,s,case,stat_layer=10)
        results["rtl"].append(r)
    # Replay the exact serialized coefficient banks, with all styles switched
    # on frame boundaries, without reset or rewriting weights.
    banks=initial_banks(q,wd);case=ext/"rtl_serialized_switch"
    if (case/"result.json").exists():r=json.loads((case/"result.json").read_text())
    else:r=rtl_case(q,np.asarray(Image.fromarray(img).resize((48,32))),0,case,
                    fixed_coefs=banks,switch=True,stat_layer=5)
    assert (case/"cfg.txt").read_bytes()==(wd/"cfg.txt").read_bytes(),"serialized deployment image mismatch"
    results["rtl"].append(r)
    photo=Image.open(ROOT.parents[2]/"710a962d5c4e21bba679555fdac3131e.jpg").convert("RGB")
    box=(int(photo.width*.25),int(photo.height*.16),int(photo.width*.89),int(photo.height*.81))
    photo=np.asarray(ImageOps.fit(photo.crop(box),(640,480),method=Image.Resampling.BILINEAR))
    rows=[photo];Image.fromarray(photo).save(ext/"screen_photo_proxy_input.png")
    for s,name in enumerate(q["styles"]):
        y,_,_=golden.run(q,photo,s)
        with torch.no_grad():f=net(torch.from_numpy(photo.copy()).permute(2,0,1)[None].float()/255,torch.tensor([s]))
        f=(f[0].permute(1,2,0).clamp(0,1).numpy()*255).round().astype(np.uint8)
        Image.fromarray(y).save(ext/f"screen_photo_proxy_{name}.png");rows.append(y)
        results["photo"].append(dict(style=name,int_vs_fp32=metric(y,f)))
    make_montage([rows],["Screen photograph proxy"]+q["styles"],ext/"screen_photo_proxy.jpg")
    results["refresh"]=refresh_check(q,wd,img)
    bounds=[]
    geo=gen_rtl.layer_geom(q,640,480)
    for L,g in zip(q["layers"],geo):
        n=g["W"]*g["H"]*(4 if L["up"] else 1)//L["stride"]**2
        acc=L["cin"]//L["groups"]*L["k"]**2*127*255
        t=(1<<18)*(1<<17)+(1<<19)*(1<<(L["S"]-8))+255*golden.skip_k(L)
        ok=acc<2**25 and t<2**39 and n*2**18<2**39 and n*2**36<2**60 and golden.skip_k(L)<2**18
        bounds.append(dict(layer=L["name"],acc_abs_bound=acc,requant_abs_bound=t,stats_n=n,pass_check=ok))
        assert ok,bounds[-1]
    results["bounds"]=bounds
    if a.art:
        # No matched content-to-art teacher exists here: report perceptual
        # distances explicitly, not a fabricated reference PSNR/SSIM.
        vgg=VGGFeat().eval();prov=json.loads((ROOT/"data/styles_art/provenance.json").read_text())
        refs=[]
        for p in prov:
            path=ROOT/"data/styles_art"/p["file"]
            assert hashlib.sha256(path.read_bytes()).hexdigest()==p["sha256"]
            with torch.no_grad():refs.append([gram(z) for z in vgg(art_tensor(path,256))])
        reference=torch.load(ROOT/"runs/art_styles_c24_strong/student.pt",map_location="cpu",weights_only=False)
        ref_net=TinyStyleNet(**reference["cfg"]).eval();ref_net.load_state_dict(reference["sd"])
        metrics=[];rowviews=[]
        for f in files[:8]:
            im=read_rgb(f);row=[im]
            with torch.no_grad():fi=vgg(torch.from_numpy(im.copy()).permute(2,0,1)[None].float()/255)
            for s,name in enumerate(q["styles"]):
                y,_,_=golden.run(q,im,s);row.append(y)
                with torch.no_grad():fy=vgg(torch.from_numpy(y.copy()).permute(2,0,1)[None].float()/255)
                with torch.no_grad():fp=ref_net(torch.from_numpy(im.copy()).permute(2,0,1)[None].float()/255,torch.tensor([s]))
                fp=(fp[0].permute(1,2,0).clamp(0,1).numpy()*255).round().astype(np.uint8)
                distance=[sum(float((gram(z)-t).square().mean()) for z,t in zip(fy,ref)) for ref in refs]
                before=sum(float((gram(z)-t).square().mean()) for z,t in zip(fi,refs[s]))
                chroma=lambda z:float(np.std(z.astype(float),axis=2).mean())
                metrics.append(dict(image=Path(f).stem,style=name,gram_before=before,gram_after=distance[s],
                                    all_reference_distances=distance,chroma_input=chroma(im),chroma_output=chroma(y),
                                    integer_vs_strong_fp32_reference=metric(y,fp)))
            if len(rowviews)<3:rowviews.append(row)
        make_montage(rowviews,["Input"]+q["styles"],ext/"art_integer_evidence.jpg")
        results["art_style_metrics"]=metrics
    results["pass_arithmetic"]=all(r["pass_check"] for r in results["rtl"])
    save_json(ext/"extra_validation.json",results)
    print("EXTRA VALIDATION PASS",a.run,flush=True)


if __name__=="__main__":main()
