"""Train the deployable C24/F16/DW-IN graph against public-domain art styles.

This is deliberately a small, auditable experiment rather than a new network:
the convolution graph stays identical to StyleCam; shared convolutions and
three style conditioning rows are trained. VGG features provide content and Gram-style
targets; the resulting checkpoint can be passed through the existing integer
export path after a calibration run.
"""
import argparse, json, os, random, time
from pathlib import Path
import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image, ImageOps

from tinystyle import TinyStyleNet, QCfg
from train import DATA, ROOT, CropSet, VGGFeat, camera_domain_augment


def gram(f):
    b, c, h, w = f.shape
    z = f.reshape(b, c, h*w)
    return torch.bmm(z, z.transpose(1, 2)) / (c*h*w)


def art_tensor(path, crop=256):
    im = Image.open(path).convert("RGB")
    # Center crop avoids borders/mounts and gives a deterministic style target.
    im = ImageOps.fit(im, (crop, crop), method=Image.Resampling.LANCZOS,
                      centering=(0.5, 0.5))
    a = np.asarray(im, dtype=np.float32) / 255.0
    return torch.from_numpy(a).permute(2, 0, 1).unsqueeze(0)


def copy_old_state(net, old_ck, row_map):
    """Copy shared convolution weights and selected IN rows from old 4-style run."""
    old = torch.load(old_ck, map_location="cpu", weights_only=False)
    oldnet = TinyStyleNet(**old["cfg"])
    oldnet.load_state_dict(old["sd"])
    sd = net.state_dict()
    for k, v in sd.items():
        if k in oldnet.state_dict() and v.shape == oldnet.state_dict()[k].shape:
            sd[k].copy_(oldnet.state_dict()[k])
    # style rows (old order candy,mosaic,rain_princess,udnie)
    for ni, oi in enumerate(row_map):
        for k in ("layers.0.norm.gamma",):
            pass
        for li, layer in enumerate(net.layers):
            if layer.norm is not None:
                layer.norm.gamma.data[ni].copy_(oldnet.layers[li].norm.gamma.data[oi])
                layer.norm.beta.data[ni].copy_(oldnet.layers[li].norm.beta.data[oi])
    net.load_state_dict(sd)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=1600)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--crop", type=int, default=256)
    ap.add_argument("--lr", type=float, default=1.5e-4)
    ap.add_argument("--out", default="runs/art_styles_c24_fp32")
    ap.add_argument("--init", default="runs/final_route_camera_temporal_fp32/student.pt")
    ap.add_argument("--resume", default="", help="continue an art checkpoint with a fresh low-rate Adam")
    ap.add_argument("--content_weight", type=float, default=0.25)
    ap.add_argument("--pixel_weight", type=float, default=0.04)
    ap.add_argument("--style_multiplier", type=float, default=1.0)
    ap.add_argument("--palette_weight", type=float, default=0.0)
    ap.add_argument("--ink_chroma_weight", type=float, default=0.0)
    ap.add_argument("--tv_weight", type=float, default=0.0)
    ap.add_argument("--hardware_contract",default="",help="frozen qparams prefix for integer-forward STE")
    ap.add_argument("--distill",default="",help="FP32 art checkpoint to preserve through quantization")
    ap.add_argument("--distill_weight",type=float,default=0.0)
    args = ap.parse_args()
    random.seed(20261004); np.random.seed(20261004); torch.manual_seed(20261004)
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    out = Path(ROOT) / args.out; out.mkdir(parents=True, exist_ok=True)
    names = ["van_gogh", "ukiyo_e", "ink_landscape"]
    files = [Path(ROOT)/"data/styles_art/van_gogh_wheat_field.jpg",
             Path(ROOT)/"data/styles_art/ukiyo_e_hokusai_great_wave.jpg",
             Path(ROOT)/"data/styles_art/ink_ni_zan_woods_valleys.jpg"]
    net = TinyStyleNet(24, 16, 4, len(names), "in", "dw1").to(dev)
    if args.resume:
        ck0 = torch.load(Path(ROOT)/args.resume, map_location="cpu", weights_only=False)
        if ck0.get("cfg") != net.cfg or ck0.get("styles") != names:
            raise SystemExit("resume checkpoint graph/style list mismatch")
        net.load_state_dict(ck0["sd"])
    else:
        copy_old_state(net, Path(ROOT)/args.init, [2, 1, 3])
    net.train(); QCfg.enabled=False; QCfg.observe=True
    contract=None;teacher=None
    if args.hardware_contract:
        import golden, hardware_qat
        contract=golden.load(args.hardware_contract)
        assert contract["cfg"]==net.cfg and contract["styles"]==names
        # CPU and CUDA float32 division can differ by one ULP. The hard
        # forward always uses the serialized contract's exact scale values.
        assert all(np.isclose(float(L.aq.scale()),q["s_y"],rtol=1e-6,atol=1e-10) for L,q in zip(net.layers,contract["layers"]))
        torch.backends.cuda.matmul.allow_tf32=False
        torch.backends.cudnn.allow_tf32=False
        QCfg.enabled=True;QCfg.observe=False
    if args.distill:
        tc=torch.load(Path(ROOT)/args.distill,map_location="cpu",weights_only=False)
        teacher=TinyStyleNet(**tc["cfg"]).to(dev).eval();teacher.load_state_dict(tc["sd"])
        for p in teacher.parameters():p.requires_grad_(False)
    vgg = VGGFeat().to(dev).eval()
    with torch.no_grad():
        style_ref = [art_tensor(p, args.crop).to(dev)
                     for p in files]
        style_feat = [vgg(s) for s in style_ref]
        style_gram = [[gram(z) for z in fs] for fs in style_feat]
    train_files, _ = __import__("train").image_list()
    dl = torch.utils.data.DataLoader(CropSet(train_files, args.crop), batch_size=args.batch,
                                     shuffle=True, drop_last=True, num_workers=0)
    opt = torch.optim.Adam(net.parameters(), lr=args.lr)
    # Three phases: stabilize identity, then make style texture visible, then
    # a short low-rate polish.  All phases use the same deployable graph.
    t0=time.time(); it=0; acc=[0.,0.,0.]
    while it < args.steps:
        for xb in dl:
            si = it % len(names)
            x = xb.to(dev).float() / 255.0
            x255 = camera_domain_augment(x*255.0, 0.35) / 255.0
            st = torch.full((x.shape[0],), si, dtype=torch.long, device=dev)
            y = (hardware_qat.forward(net,x255,st,contract) if contract else net(x255, st)).clamp(0, 1)
            with torch.no_grad():
                fx = vgg(x)
            fy = vgg(y)
            # VGG content at relu3_3 preserves scene structure.  Lower-layer
            # Gram terms carry brush/line/pigment statistics of each artwork.
            lc = F.mse_loss(fy[-1], fx[-1])
            ls = sum(F.mse_loss(gram(a), b.expand(a.shape[0], -1, -1))
                     for a,b in zip(fy, style_gram[si]))
            lp = F.l1_loss(y, x)
            phase = it / max(args.steps, 1)
            # Strong enough style signal without allowing a single image's
            # palette to erase camera content.
            ws = 500.0 if phase < .20 else (900.0 if phase < .85 else 650.0)
            ref = style_ref[si]
            palette = F.mse_loss(y.mean((2, 3)), ref.mean((2, 3)).expand(y.shape[0], -1))
            palette += F.mse_loss(y.std((2, 3)), ref.std((2, 3)).expand(y.shape[0], -1))
            chroma = (y - y.mean(1, keepdim=True)).square().mean() if si == 2 else y.new_zeros(())
            tv = (y[:, :, 1:] - y[:, :, :-1]).abs().mean() + (y[:, :, :, 1:] - y[:, :, :, :-1]).abs().mean()
            loss = (args.content_weight*lc + args.pixel_weight*lp + ws*args.style_multiplier*ls
                    + args.palette_weight*palette + args.ink_chroma_weight*chroma + args.tv_weight*tv)
            if teacher is not None:
                enabled=QCfg.enabled;QCfg.enabled=False
                with torch.no_grad():yt=teacher(x255,st).clamp(0,1)
                QCfg.enabled=enabled
                loss+=args.distill_weight*F.l1_loss(y,yt)
            QCfg.observe = phase < .9 and contract is None
            opt.zero_grad(set_to_none=True); loss.backward()
            torch.nn.utils.clip_grad_norm_(net.parameters(), 1.0)
            opt.step(); it += 1
            acc[0]+=float(loss); acc[1]+=float(lc); acc[2]+=float(ls)
            if it % 200 == 0:
                print(f"it {it}/{args.steps} loss {acc[0]/200:.5f} content {acc[1]/200:.5f} gram {acc[2]/200:.7f} {time.time()-t0:.0f}s",flush=True)
                acc=[0.,0.,0.]
            if it >= args.steps: break
    ck={"cfg":net.cfg,"styles":names,"sd":net.state_dict(),"qat":bool(contract),"it":it,
        "args":vars(args),"style_sources":[str(p) for p in files],
        "style_training":"VGG relu3_3 content + relu2_2/relu3_3 Gram; optional palette/chroma/TV"}
    torch.save(ck, out/"student.pt")
    (out/"style_training.json").write_text(json.dumps({"styles":names,"sources":[str(p) for p in files],"steps":it,"device":dev,"seconds":time.time()-t0,"args":vars(args),"init":args.resume or args.init},ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"saved {out/'student.pt'}")


if __name__ == "__main__": main()
