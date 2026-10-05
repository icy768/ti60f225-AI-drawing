"""Isolated PC acceptance of a real checkpoint and its exported integer contract.

Run from the repository with its working Python environment. Results are staged
under an ASCII path for MinGW/Icarus. Deployed firmware and RTL are never written.
Dynamic current-frame IN is an arithmetic oracle, not the deployed refresh policy.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

import numpy as np
from PIL import Image, ImageDraw, ImageOps
import torch

import gen_rtl
import golden
from sim_in_refresh import run_with_coefs
from tinystyle import TinyStyleNet, QCfg, macs_per_pixel, param_count
from train import ROOT, image_list

ROOT = Path(ROOT)


def save_json(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def metric(a, b):
    from skimage.metrics import structural_similarity
    mse = float(np.mean((a.astype(float)-b.astype(float))**2))
    return {"psnr": float(10*np.log10(255**2/mse)) if mse else None, "exact_match":mse==0,
            "ssim": float(structural_similarity(a, b, channel_axis=2, data_range=255)),
            "mae": float(np.abs(a.astype(float)-b.astype(float)).mean())}


def read_rgb(path, size=(640, 480)):
    return np.asarray(ImageOps.fit(Image.open(path).convert("RGB"), size, method=Image.Resampling.BILINEAR))


def pack(a):
    z = a.astype(np.uint32)
    return z[..., 0] | (z[..., 1] << 8) | (z[..., 2] << 16)


def firmware(q, stats, style, wd):
    inp = wd / "stats.txt"
    inp.write_text("".join(f"{i} {c} {int(a)} {int(b)}\n" for i, st in enumerate(stats)
                           if st is not None for c, (a,b) in enumerate(zip(st[0],st[1]))), encoding="ascii")
    subprocess.run([str(wd/"host_test.exe"), "stats.txt", "events.txt", str(style)], cwd=wd, check=True)
    expected = {i: golden.coef_from_stats(L, stats[i], style) for i,L in enumerate(q["layers"]) if stats[i] is not None}
    dm = db = count = 0
    rounds, current = [], []
    def sx(v, bits):
        return v - (1 << bits) if v & (1 << (bits-1)) else v
    for line in (wd/"events.txt").read_text().splitlines():
        e = line.split()
        if e[0] == "cfg":
            addr,lo,hi = map(int,e[1:])
            layer,idx = (addr >> 16)&31, addr&4095
            bank,c = divmod(idx,q["layers"][layer]["cout"])
            m,b = sx(((hi&63)<<12)|(lo>>20),18), sx(lo&1048575,20)
            dm=max(dm,abs(m-int(expected[layer][0][c])))
            db=max(db,abs(b-int(expected[layer][1][c])))
            current.append((layer,bank)); count += 1
        elif e[0] == "style":
            rounds.append((int(e[1]),list(set(current))));current=[]
    nl=len(expected)
    bank_ok = (len(rounds)==2*nl+1 and all(r[0] in (2*style,2*style+1) for r in rounds)
               and all(all(bank==r[0] for _,bank in r[1]) for r in rounds[1:])
               and all(rounds[i][0]!=rounds[i+1][0] for i in range(len(rounds)-1)))
    # Each refresh also copies the preceding update into the other bank;
    # the first refresh has no preceding update to copy.
    expected_count = 4*sum(q["layers"][i]["cout"] for i in expected)-q["layers"][max(expected)]["cout"]
    result=dict(max_M_error=dm,max_B_error=db,writes=count,expected_writes=expected_count,
                bank_ok=bank_ok,rounds=len(rounds),pass_check=dm<=1 and db<=1 and bank_ok and count==expected_count)
    shutil.copy2(wd/"events.txt",wd/f"events_style{style}.txt")
    assert result["pass_check"], result
    return result


def rtl_case(q, img, style, wd, *, load=True, stat_layer=5, nframes=1, fixed_coefs=None, switch=False):
    wd.mkdir(parents=True,exist_ok=True)
    H,W=img.shape[:2]
    if fixed_coefs is None:
        refs=[golden.run(q,img,s,dump=True) for s in range(len(q["styles"]))]
        coefs=[([refs[s][2][i]["M"] for s in range(len(refs)) for _ in range(2)],
                [refs[s][2][i]["B"] for s in range(len(refs)) for _ in range(2)]) for i in range(len(q["layers"]))]
        out,stats,dumps=refs[style]
    else:
        coefs=fixed_coefs
        refs=[]
        for s in range(len(q["styles"])):
            x=torch.from_numpy(img.copy()).permute(2,0,1)[None].double()
            feats=[];sts=[];ds=[]
            for i,L in enumerate(q["layers"]):
                aa=golden.shift_sat(golden.conv_int(x,L),L["R"])
                sts.append(golden.stats(aa) if "gamma" in L else None)
                m,b=coefs[i][0][2*s+1],coefs[i][1][2*s+1]
                x=golden.requant(aa,L,m,b,feats[L["skip"]] if L["skip"] is not None else None)
                feats.append(x);ds.append(dict(a=aa[0].long().numpy(),q=x[0].byte().numpy(),M=m,B=b))
            y=torch.nn.functional.pixel_shuffle(x,2)[0].permute(1,2,0).byte().numpy()
            refs.append((y,sts,ds))
        out,stats,dumps=refs[style]
    if switch:
        nframes=len(q["styles"])
    geo,_=gen_rtl.generate(q,W,H,str(wd),coefs,2*len(q["styles"]),embed=not load,relative_mem=True)
    np.savetxt(wd/"in.hex",np.tile(pack(img).flatten(),nframes),fmt="%06x")
    gen_rtl.make_tb(str(wd),len(geo),W,H,nframes,19,3,7,int(load),stat_layer,
                    q["layers"][stat_layer]["cout"],bank=2*style+1)
    if switch:
        tb=(wd/"tb_top.v").read_text()
        tb=tb.replace(f".style(4'd{2*style+1})", ".style(switch_bank)")
        tb=tb.replace("    stylenet_top dut", "    wire [3:0] switch_bank = 2 * (op / (W*H)) + 1;\n    stylenet_top dut")
        tb=tb.replace("< NPX)", "< NPX) && (((in_v && in_r) ? ip + 1 : ip) < ((op / (W*H)) + 1) * (W*H))")
        (wd/"tb_top.v").write_text(tb)
    log=gen_rtl.simulate(str(wd));(wd/"simulation.log").write_text("\n".join(log),encoding="utf-8")
    all_layers=[]
    for i,d in enumerate(dumps):
        a=d["q"].transpose(1,2,0).reshape(-1,4).astype(np.uint32)
        exp=np.tile(a[:,0]|(a[:,1]<<8)|(a[:,2]<<16)|(a[:,3]<<24),nframes)
        if switch:
            arrays=[r[2][i]["q"].transpose(1,2,0).reshape(-1,4).astype(np.uint32) for r in refs]
            exp=np.concatenate([a[:,0]|(a[:,1]<<8)|(a[:,2]<<16)|(a[:,3]<<24) for a in arrays])
        got=np.array(gen_rtl.read_words(wd/f"l{i}.hex",32),dtype=np.int64)
        bad=int(np.count_nonzero(got[:min(len(got),len(exp))]!=exp[:min(len(got),len(exp))]))+abs(len(got)-len(exp))
        all_layers.append(dict(layer=i,name=q["layers"][i]["name"],words=len(got),expected=len(exp),mismatch=bad))
    got=np.array(gen_rtl.read_words(wd/"out.hex",24),dtype=np.int64)
    exp=np.concatenate([pack(r[0]).flatten() for r in refs]) if switch else np.tile(pack(out).flatten(),nframes)
    pixels_ok=np.array_equal(got,exp)
    rows=(wd/"stats.txt").read_text().splitlines()
    gs1,gs2,_=stats[stat_layer]
    hs=np.array([list(map(int,row.split())) for row in rows[:-1]],dtype=np.int64)
    # Stats unit covers the armed interval: all frames in this direct-stream TB.
    es1=sum(r[1][stat_layer][0] for r in refs) if switch else gs1*nframes
    es2=sum(r[1][stat_layer][1] for r in refs) if switch else gs2*nframes
    st_ok=(len(hs)==len(gs1) and np.array_equal(hs[:,0],es1)
           and np.array_equal(hs[:,1],es2) and rows[-1]=="done 1")
    result=dict(style=q["styles"][style],bank=2*style+1,W=W,H=H,nframes=nframes,load=load,
                layers=all_layers,pixels_ok=pixels_ok,stats_ok=bool(st_ok),stat_layer=stat_layer,
                cycles=int(re.search(r"DONE cycles=(\d+)","\n".join(log))[1]))
    result.update(coefficient_mode="exported_initial_banks" if fixed_coefs is not None else "same_frame_oracle",
                  switch_without_reset=switch,simulator=os.environ.get("STYLECAM_SIMULATOR","iverilog"))
    result["pass_check"]=pixels_ok and bool(st_ok) and all(x["mismatch"]==0 for x in all_layers)
    save_json(wd/"result.json",result)
    assert result["pass_check"],result
    print("RTL PASS",q["styles"][style],W,H,"layers",len(all_layers),flush=True)
    return result


def blob_check(q, wd):
    words=np.fromfile(wd/"net_blob.bin",dtype="<u4")
    assert words[0]==0x53544e31 and words[2]==len(q["styles"]) and len(words)==4+3*int(words[1])
    script=[line.split() for line in (wd/"cfg.txt").read_text().splitlines()]
    assert len(script)==int(words[1])
    for row,w in zip(script,words[4:].reshape(-1,3)):
        layer,sel,lane,addr=map(int,row[:4]);data=int(row[4],16)
        assert list(map(int,w))==[(sel<<31)|(lane<<21)|(layer<<16)|addr,data&0xffffffff,(data>>32)&63]
    assert len(words)*4 < 500000
    return dict(bytes=words.nbytes,cfg_writes=len(script),sha256=sha(wd/"net_blob.bin"),pass_check=True)


def make_montage(rows, labels, path):
    w,h=320,240
    out=Image.new("RGB",(w*len(labels),(h+24)*len(rows)),"white")
    draw=ImageDraw.Draw(out)
    for ri,row in enumerate(rows):
        for ci,a in enumerate(row):
            out.paste(Image.fromarray(a).resize((w,h)),(ci*w,ri*(h+24)+24))
            draw.text((ci*w+6,ri*(h+24)+5),labels[ci],fill="black")
    out.save(path,quality=94)


def refresh_check(q, wd, img):
    initial=[]
    for i,L in enumerate(q["layers"]):
        h=[int(x,16) for x in (wd/f"c{i}_{L['name']}.mem").read_text().splitlines()]
        z=np.array([h[j]|(h[j+1]<<19) for j in range(0,len(h),2)],np.int64).reshape(2*len(q["styles"]),L["cout"])
        m=(z>>20)&262143;b=z&1048575
        initial.append((np.where(m&131072,m-262144,m),np.where(b&524288,b-1048576,b)))
    res=[]
    for s,name in enumerate(q["styles"]):
        oracle,_,_=golden.run(q,img,s)
        co=[(a[2*s].copy(),b[2*s].copy()) if "gamma" in L else None for (a,b),L in zip(initial,q["layers"])]
        ids=[i for i,L in enumerate(q["layers"]) if "gamma" in L]
        values=[]
        for t in range(25):
            y,sts=run_with_coefs(q,img,co)
            if t in (0,12,24):
                values.append(dict(frame=t,**metric(y,oracle)))
                Image.fromarray(y).save(wd/f"refresh_{name}_{t}.png")
            li=ids[t%len(ids)];co[li]=golden.coef_from_stats(q["layers"][li],sts[li],s)
        # A controlled exposure change, explicitly not a real camera video.
        dark=(img.astype(float)*.55).round().astype(np.uint8)
        target,_,_=golden.run(q,dark,s)
        motion=[]
        for t in range(25):
            y,sts=run_with_coefs(q,dark,co)
            if t in (0,6,12,18,24): motion.append(dict(frame=t,**metric(y,target)))
            li=ids[(25+t)%len(ids)];co[li]=golden.coef_from_stats(q["layers"][li],sts[li],s)
        res.append(dict(style=name,static=values,synthetic_exposure_step=motion))
    save_json(wd/"refresh.json",res)
    return res


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--run",required=True)
    ap.add_argument("--stage",default="C:/CodexTemp/stylecam_pc_20261004")
    ap.add_argument("--ncal",type=int,default=8)
    ap.add_argument("--neval",type=int,default=8)
    ap.add_argument("--vga_rtl",action="store_true")
    ap.add_argument("--refresh",action="store_true")
    ap.add_argument("--skip_export",action="store_true")
    ap.add_argument("--verilator",action="store_true")
    ap.add_argument("--contract",default="",help="freeze exported R/S shifts to an existing integer contract")
    a=ap.parse_args();torch.set_num_threads(4)
    stage=Path(a.stage);wd=stage/Path(a.run).name;wd.mkdir(parents=True,exist_ok=True)
    sw=wd/"sw";sw.mkdir(exist_ok=True)
    toolsbin=Path("C:/CodexTemp/ds8_rtl_tools/mingw64/bin")
    os.environ["PATH"]=str(toolsbin)+os.pathsep+"C:/mingw64/bin"+os.pathsep+os.environ["PATH"]
    gen_rtl.IVERILOG=str(toolsbin/"iverilog.exe");gen_rtl.VVP=str(toolsbin/"vvp.exe")
    rtl=stage/"rtl";rtl.mkdir(exist_ok=True)
    for f in (ROOT/"rtl").glob("*.v"):shutil.copy2(f,rtl/f.name)
    gen_rtl.RTL=str(rtl)
    if a.verilator:
        from pc_extra_validate import simulate_verilator
        gen_rtl.simulate=simulate_verilator
        os.environ["STYLECAM_SIMULATOR"]="verilator-python 5.48.0"
    if not a.skip_export:
        export_cmd=[sys.executable,"-X","utf8","-u",str(ROOT/"algo/export_blob.py"),"--run",a.run,"--outdir",str(wd),
                    "--swdir",str(sw),"--ncal",str(a.ncal),"--skip_eval","--cal_vga"]
        if a.contract:export_cmd.extend(["--contract",a.contract])
        proc=subprocess.run(export_cmd,capture_output=True,text=True,encoding="utf-8")
        (wd/"export.log").write_text(proc.stdout+proc.stderr,encoding="utf-8")
        assert proc.returncode==0,proc.stdout+proc.stderr
    q=golden.load(str(wd/"qparams"));res={"run":a.run,"styles":q["styles"],"blob":blob_check(q,wd)}
    for f in ("vision.c","vision.h","hal.h"):shutil.copy2(ROOT/"sw"/f,sw/f)
    shutil.copy2(ROOT/"sw/test/host_test.c",sw/"host_test.c")
    subprocess.run(["C:/mingw64/bin/gcc.exe","-O2","-Wall","-D__USE_MINGW_ANSI_STDIO=1","-DVISION_HOST_TEST","-I.",
                    "host_test.c","vision.c","-lm","-o","host_test.exe"],cwd=sw,check=True,capture_output=True)
    ck=torch.load(ROOT/a.run/"student.pt",map_location="cpu",weights_only=False)
    net=TinyStyleNet(**ck["cfg"]).eval();net.load_state_dict(ck["sd"]);QCfg.enabled=False;QCfg.observe=False
    _,files=image_list(); imgs=[(Path(f).stem,read_rgb(f)) for f in files[:a.neval]]
    photo=ROOT.parents[2]/"710a962d5c4e21bba679555fdac3131e.jpg"
    if photo.exists():
        p=Image.open(photo).convert("RGB")
        # Approximate screen interior only. This is a screen re-photograph,
        # not sensor RGB; no color/geometry correction is applied.
        p=p.crop((int(p.width*.25),int(p.height*.16),int(p.width*.89),int(p.height*.81)))
        imgs.append(("screen_photo_proxy",np.asarray(ImageOps.fit(p,(640,480),method=Image.Resampling.BILINEAR))))
    visual=wd/"images";visual.mkdir(exist_ok=True)
    res["quality"]=[];res["firmware"]=[];montages=[]
    for j,(name,img) in enumerate(imgs):
        row=[img];Image.fromarray(img).save(visual/f"{name}_input.png")
        for s,sty in enumerate(q["styles"]):
            with torch.no_grad():
                y=net(torch.from_numpy(img.copy()).permute(2,0,1)[None].float()/255,torch.tensor([s]))
            fp=(y[0].permute(1,2,0).clamp(0,1).numpy()*255).round().astype(np.uint8)
            out,stats,dumps=golden.run(q,img,s,dump=True)
            boundaries=[dict(layer=i,A_boundary=int(np.count_nonzero((d["a"]==-262144)|(d["a"]==262143))),
                             M_boundary=int(np.count_nonzero((d["M"]==-131072)|(d["M"]==131071))),
                             B_boundary=int(np.count_nonzero((d["B"]==-524288)|(d["B"]==524287)))) for i,d in enumerate(dumps)]
            res["quality"].append(dict(image=name,style=sty,int_vs_fp32=metric(out,fp),coefficient_boundaries=boundaries))
            Image.fromarray(fp).save(visual/f"{name}_{sty}_fp32.png")
            Image.fromarray(out).save(visual/f"{name}_{sty}_int.png")
            row.append(out)
            if j==0:res["firmware"].append(dict(style=sty,**firmware(q,stats,s,sw)))
        if j<4 or name=="screen_photo_proxy":montages.append(row)
        print("EVAL",a.run,name,flush=True)
    make_montage(montages,["Input"]+q["styles"],wd/"integer_styles.jpg")
    save_json(wd/"validation.json",res)
    base=np.asarray(Image.fromarray(imgs[0][1]).resize((48,32)))
    res["rtl"]=[]
    for s in range(len(q["styles"])):
        res["rtl"].append(rtl_case(q,base,s,wd/f"rtl_style{s}",stat_layer=[0,5,10,11][s],nframes=2 if s==0 else 1))
    # Embedded initial contents take a different load path from cfg writes.
    res["rtl"].append(rtl_case(q,np.full_like(base,127),0,wd/"rtl_flat",load=False,stat_layer=1))
    if a.vga_rtl:res["rtl"].append(rtl_case(q,imgs[0][1],0,wd/"rtl_vga",stat_layer=10))
    if a.refresh:res["refresh"]=refresh_check(q,wd,imgs[0][1])
    res["macs_vga"]=macs_per_pixel(net.specs)[0]*640*480
    res["parameters"]=param_count(net.specs,len(q["styles"]))
    res["pass_arithmetic"]=True
    res["limits"]=["No physical FPGA", "No raw camera video", "Dynamic-IN RTL oracle is not refresh-policy equivalence",
                    "PC cycles are not board FPS", "Art style quality requires visual review"]
    save_json(wd/"validation.json",res)
    print("CANDIDATE PC ARITHMETIC PASS",wd,flush=True)


if __name__=="__main__":main()
