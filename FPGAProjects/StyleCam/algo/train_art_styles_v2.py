"""Train a stronger, multi-reference art-style checkpoint.

The deployable graph remains the C24/F16/4-dw1 conditional-IN network.  This
script changes only the offline objective: many traceable artwork references,
style-specific color/edge statistics, and a stronger style phase.  Candidate
images marked as holdout in proposed_split.json are never loaded.
"""
from __future__ import annotations
import argparse, json, random, time
from pathlib import Path
import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image, ImageOps

from tinystyle import TinyStyleNet, QCfg
from train import ROOT, CropSet, VGGFeat, camera_domain_augment, image_list
from train_art_styles import gram

STYLE_NAMES = ["van_gogh", "ukiyo_e", "ink_landscape"]
MANIFEST = Path(ROOT) / "dataset_v2/manifests/met_candidates.jsonl"
SPLIT = Path(ROOT) / "dataset_v2/manifests/proposed_split.json"

def style_paths():
    rows = [json.loads(x) for x in MANIFEST.read_text(encoding="utf-8").splitlines() if x.strip()]
    split = json.loads(SPLIT.read_text(encoding="utf-8"))
    excluded = {int(x) for s in split.get("summary", {}).values() for x in []}
    # proposed_split stores counts only; the holdout IDs are encoded in the
    # organized manifest and are explicitly excluded below.
    organized = Path(ROOT) / "dataset_v2/manifests/met_candidates_organized.jsonl"
    by_id = {}
    if organized.exists():
        for x in organized.read_text(encoding="utf-8").splitlines():
            if x.strip():
                r = json.loads(x); by_id[int(r["object_id"])] = r.get("candidate_role", "candidate")
    out = {s: [] for s in STYLE_NAMES}
    for r in rows:
        if r.get("download") != "ok": continue
        oid = int(r["object_id"])
        if by_id.get(oid) == "holdout": continue
        medium = (r.get("medium") or "").lower()
        title = (r.get("title") or "").lower()
        style = r["style"]
        artist = (r.get("artist") or "").lower()
        ok = False
        out_style = "ink_landscape" if style == "ink_wash" else style
        if style == "van_gogh":
            # Oil-on-canvas supplies the desired pigment/impasto target. A
            # small number of older oil works are retained for variation.
            ok = "vincent van gogh" in artist and "oil on canvas" in medium
        elif style == "ukiyo_e":
            ok = "woodblock print" in medium and "ink" in medium and "color" in medium
        elif style == "ink_wash":
            reject = ("calligraphy", "letter", "poem", "text", "preface", "designs", "copy after", "filial")
            ok = ("ink" in medium and any(x in medium for x in ("paper", "silk", "satin"))
                  and "woodblock" not in medium and not any(x in title for x in reject))
        if ok: out[out_style].append(Path(ROOT) / "dataset_v2" / r["path"])
    # Keep every eligible reference up to a bounded, deterministic budget.
    # More references are useful for style statistics, but a few hundred VGG
    # passes unnecessarily slow iteration on the 8 GB GPU.
    caps = {"van_gogh": 24, "ukiyo_e": 36, "ink_landscape": 28}
    return {s: sorted(v)[:caps[s]] for s, v in out.items()}

def art_tensor(path, crop=256, view=0):
    im = Image.open(path).convert("RGB")
    if view == 0:
        im = ImageOps.fit(im, (crop, crop), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
    else:
        # Deterministic off-center views preserve brush/line evidence near the
        # edges while keeping the VGG target size fixed.
        c = (0.35, 0.65) if view == 1 else (0.65, 0.35)
        im = ImageOps.fit(im, (crop, crop), method=Image.Resampling.LANCZOS, centering=c)
    a = np.asarray(im, dtype=np.float32) / 255.0
    return torch.from_numpy(a).permute(2, 0, 1).unsqueeze(0)

def sobel_stats(x):
    gray = (0.299*x[:,0:1] + 0.587*x[:,1:2] + 0.114*x[:,2:3])
    kx = x.new_tensor([[-1,0,1],[-2,0,2],[-1,0,1]]).view(1,1,3,3) / 8
    ky = kx.transpose(2,3)
    dx = F.conv2d(gray, kx, padding=1); dy = F.conv2d(gray, ky, padding=1)
    mag = torch.sqrt(dx.square() + dy.square() + 1e-6)
    return mag.mean((2,3)), mag.std((2,3))

def palette_stats(x):
    sat = x.amax(1) - x.amin(1)
    return torch.cat([x.mean((2,3)), x.std((2,3)), sat.mean((1,2), keepdim=True).flatten(1), sat.std((1,2), keepdim=True).flatten(1)], 1)

def proxy_target(x, style):
    """Construct a deterministic, deployable-style visual target from a photo.

    This is a training prior, not a post-processing stage. It supplies the
    small network with spatial cues that global Gram statistics do not encode.
    """
    gray = 0.299*x[:,0:1] + 0.587*x[:,1:2] + 0.114*x[:,2:3]
    kx = x.new_tensor([[-1,0,1],[-2,0,2],[-1,0,1]]).view(1,1,3,3) / 8
    ky = kx.transpose(2,3)
    edge = torch.sqrt(F.conv2d(gray,kx,padding=1).square() + F.conv2d(gray,ky,padding=1).square() + 1e-6)
    edge = (edge / (edge.mean((2,3),keepdim=True)+1e-5)).clamp(0, 2)
    if style == "van_gogh":
        # Complementary blue/yellow bias plus a restrained local contrast term.
        lum = gray
        warm = torch.cat([lum*1.18, lum*1.03, lum*0.72], 1)
        cool = torch.cat([lum*0.62, lum*0.82, lum*1.22], 1)
        mask = (lum - 0.48).tanh().mul(0.5).add(0.5)
        y = x.mean(1,keepdim=True) + 1.28*(x-x.mean(1,keepdim=True))
        y = 0.62*y + 0.24*warm*mask + 0.24*cool*(1-mask)
        return y.clamp(0,1)
    if style == "ukiyo_e":
        # Quantized paint blocks with a dark, continuous edge drawing.
        q = torch.round(x*5.0)/5.0
        return (q*(1.0-0.42*edge.clamp(0,1))).clamp(0,1)
    # Ink: grayscale wash, black ink edges, and a bright paper/highlight floor.
    g = gray.repeat(1,3,1,1)
    g = (g-0.5)*1.55 + 0.60
    y = g - 0.38*edge.clamp(0,1)
    return y.clamp(0,1)

def make_targets(refs, vgg, device):
    targets = {}
    with torch.no_grad():
        for style, paths in refs.items():
            arr=[]
            for p in paths:
                for view in (0,1,2):
                    x=art_tensor(p,256,view).to(device)
                    f=vgg(x)
                    arr.append({"gram":[gram(z).detach() for z in f],
                                "palette":palette_stats(x).detach(),
                                "edge":torch.cat(sobel_stats(x),1).detach(),
                                "gray":(0.299*x[:,0:1]+0.587*x[:,1:2]+0.114*x[:,2:3]).mean().detach(),
                                "path":str(p),"view":view})
            targets[style]=arr
    return targets

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--steps",type=int,default=3200)
    ap.add_argument("--batch",type=int,default=4)
    ap.add_argument("--crop",type=int,default=256)
    ap.add_argument("--lr",type=float,default=7e-5)
    ap.add_argument("--out",default="runs/art_styles_c24_strong_v2")
    ap.add_argument("--init",default="runs/art_styles_c24_strong/student.pt")
    ap.add_argument("--style_weight",type=float,default=1200.0)
    ap.add_argument("--content_weight",type=float,default=0.018)
    ap.add_argument("--palette_weight",type=float,default=5.0)
    ap.add_argument("--edge_weight",type=float,default=2.0)
    ap.add_argument("--ink_chroma_weight",type=float,default=7.0)
    ap.add_argument("--tv_weight",type=float,default=0.008)
    ap.add_argument("--proxy_weight",type=float,default=0.32)
    args=ap.parse_args()
    random.seed(20261005); np.random.seed(20261005); torch.manual_seed(20261005)
    dev="cuda" if torch.cuda.is_available() else "cpu"
    out=Path(ROOT)/args.out; out.mkdir(parents=True,exist_ok=True)
    refs=style_paths(); print(json.dumps({k:[str(p) for p in v] for k,v in refs.items()},ensure_ascii=False,indent=2),flush=True)
    # Reuse the graph and prior art checkpoint. This makes the strong-style
    # run fast to converge while preserving the previously validated topology.
    ck=torch.load(Path(ROOT)/args.init,map_location="cpu",weights_only=False)
    net=TinyStyleNet(**ck["cfg"]).to(dev); net.load_state_dict(ck["sd"]); net.train()
    QCfg.enabled=False; QCfg.observe=False
    vgg=VGGFeat().to(dev).eval()
    targets=make_targets(refs,vgg,dev)
    files,_=image_list()
    dl=torch.utils.data.DataLoader(CropSet(files,args.crop),batch_size=args.batch,shuffle=True,drop_last=True,num_workers=0)
    opt=torch.optim.Adam(net.parameters(),lr=args.lr)
    t0=time.time(); acc=np.zeros(7,dtype=np.float64); it=0
    while it<args.steps:
        for xb in dl:
            si=it%3; style=STYLE_NAMES[si]; x=xb.to(dev).float()/255.0
            x255=camera_domain_augment(x*255.0,0.45)/255.0
            st=torch.full((x.shape[0],),si,dtype=torch.long,device=dev)
            y=net(x255,st).clamp(0,1)
            yp=proxy_target(x255,style)
            with torch.no_grad(): fx=vgg(x)
            fy=vgg(y)
            t=targets[style][(it*5+it//3)%len(targets[style])]
            ls=sum(F.mse_loss(gram(a),b.expand(a.shape[0],-1,-1)) for a,b in zip(fy,t["gram"]))
            lc=F.mse_loss(fy[-1],fx[-1])
            ps=F.mse_loss(palette_stats(y),t["palette"].expand(x.shape[0],-1))
            es=F.mse_loss(torch.cat(sobel_stats(y),1),t["edge"].expand(x.shape[0],-1))
            lproxy=F.l1_loss(y,yp)
            # Style-specific aggressive shaping. Ink suppresses chroma;
            # Van Gogh boosts saturation; Ukiyo-e uses modest flattening while
            # retaining strong boundaries through the edge target.
            sat=(y.amax(1)-y.amin(1)).mean()
            ink_chroma=(y-y.mean(1,keepdim=True)).square().mean()
            if style=="van_gogh": shape=-0.12*sat
            elif style=="ukiyo_e": shape=0.008*((y[:,:,1:]-y[:,:,:-1]).square().mean()+(y[:,:,:,1:]-y[:,:,:,:-1]).square().mean())
            else: shape=args.ink_chroma_weight*ink_chroma
            tv=(y[:,:,1:]-y[:,:,:-1]).abs().mean()+(y[:,:,:,1:]-y[:,:,:,:-1]).abs().mean()
            phase=it/max(args.steps,1)
            sw=args.style_weight*(1.25 if phase>0.18 and phase<0.82 else 0.85)
            loss=sw*ls+args.content_weight*lc+args.palette_weight*ps+args.edge_weight*es+args.proxy_weight*lproxy+shape+args.tv_weight*tv
            opt.zero_grad(set_to_none=True); loss.backward(); torch.nn.utils.clip_grad_norm_(net.parameters(),1.0); opt.step()
            vals=[float(loss),float(ls),float(lc),float(ps),float(es),float(sat),float(ink_chroma)]; acc+=vals; it+=1
            if it%200==0:
                print(f"it {it}/{args.steps} loss {acc[0]/200:.5f} gram {acc[1]/200:.7f} content {acc[2]/200:.5f} palette {acc[3]/200:.5f} edge {acc[4]/200:.5f} sat {acc[5]/200:.4f} chroma {acc[6]/200:.5f} {time.time()-t0:.0f}s",flush=True); acc*=0
            if it>=args.steps: break
    names=STYLE_NAMES
    torch.save({"cfg":net.cfg,"styles":names,"sd":net.state_dict(),"qat":False,"it":it,"args":vars(args),"style_sources":{k:[str(p) for p in v] for k,v in refs.items()},"style_training":"multi-reference VGG Gram + palette + Sobel edge statistics; style-specific saturation/ink shaping"},out/"student.pt")
    (out/"style_training.json").write_text(json.dumps({"styles":names,"steps":it,"device":dev,"seconds":time.time()-t0,"args":vars(args),"references":{k:[str(p) for p in v] for k,v in refs.items()}},ensure_ascii=False,indent=2),encoding="utf-8")
    print("saved",out/"student.pt",flush=True)

if __name__=="__main__": main()
