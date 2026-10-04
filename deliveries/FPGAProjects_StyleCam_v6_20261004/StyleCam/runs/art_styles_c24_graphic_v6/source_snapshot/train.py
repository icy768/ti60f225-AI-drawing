# 知识蒸馏训练 TinyStyleNet：教师 = Johnson 预训练模型，损失 = L1 + VGG 感知损失
# 前 qat_frac 比例迭代为浮点训练，之后开启伪量化做 QAT，最后 10% 冻结激活量程
import argparse
import glob
import json
import math
import os
import random
import time
import warnings

import torch
import torch.nn.functional as F
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from torchvision import models

from teacher import load_teacher
from tinystyle import QCfg, TinyStyleNet, buffer_bytes, macs_per_pixel, param_count

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
N_EVAL = 200


def set_seed(seed):
    """Make route comparisons reproducible where CUDA permits it."""
    if seed is None:
        return
    random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def camera_domain_augment(x, probability=1.0):
    """Approximate mild SC431HAI/ISP variation for training only.

    x is BCHW in the 0..255 domain.  The transform deliberately stays
    low-amplitude: it changes exposure, channel gain, gamma and sensor noise,
    but does not change geometry or add an inference-time operator.
    """
    if probability <= 0:
        return x
    keep = (torch.rand((x.shape[0], 1, 1, 1), device=x.device) < probability)
    gain = torch.empty((x.shape[0], 1, 1, 1), device=x.device).uniform_(0.90, 1.10)
    channel = torch.empty((x.shape[0], 3, 1, 1), device=x.device).uniform_(0.96, 1.04)
    gamma = torch.empty((x.shape[0], 1, 1, 1), device=x.device).uniform_(0.92, 1.08)
    z = (x / 255.0).clamp(0, 1)
    z = (z * gain * channel).clamp(0, 1)
    z = z.pow(gamma)
    z = z * 255.0
    z = z + torch.randn_like(z) * 0.7
    z = z.clamp(0, 255)
    return torch.where(keep, z, x)


def temporal_shift_pair(x, max_shift):
    """Create a translated training pair and valid overlap slices.

    The pair is only used for a training loss.  There is no recurrent state,
    optical flow, or extra FPGA operator at inference time.
    """
    if max_shift <= 0:
        return x, (slice(None), slice(None), slice(None), slice(None))
    dy = int(torch.randint(-max_shift, max_shift + 1, ()).item())
    dx = int(torch.randint(-max_shift, max_shift + 1, ()).item())
    if dy == 0 and dx == 0:
        dx = 1 if x.shape[-1] > 1 else 0
    pair = torch.roll(x, (dy, dx), dims=(2, 3))
    h, w = x.shape[-2:]
    y0, y1 = max(0, dy), min(h, h + dy)
    x0, x1 = max(0, dx), min(w, w + dx)
    oy0, oy1 = y0 - dy, y1 - dy
    ox0, ox1 = x0 - dx, x1 - dx
    return pair, (slice(y0, y1), slice(x0, x1), slice(oy0, oy1), slice(ox0, ox1))


def image_list():
    files = sorted(glob.glob(os.path.join(DATA, "val2017", "*.jpg")))
    return files[:-N_EVAL], files[-N_EVAL:]


class CropSet(Dataset):
    def __init__(self, files, crop):
        self.files, self.crop = files, crop

    def __len__(self):
        return len(self.files)

    def __getitem__(self, i):
        im = Image.open(self.files[i]).convert("RGB")
        w, h = im.size
        if min(w, h) < self.crop:
            r = self.crop / min(w, h)
            im = im.resize((math.ceil(w * r), math.ceil(h * r)), Image.BICUBIC)
            w, h = im.size
        x, y = random.randint(0, w - self.crop), random.randint(0, h - self.crop)
        im = im.crop((x, y, x + self.crop, y + self.crop))
        if random.random() < 0.5:
            im = im.transpose(Image.FLIP_LEFT_RIGHT)
        t = torch.frombuffer(bytearray(im.tobytes()), dtype=torch.uint8)
        return t.view(self.crop, self.crop, 3).permute(2, 0, 1).contiguous()


def gram(f):
    b, c, h, w = f.shape
    f = f.view(b, c, h * w)
    return torch.bmm(f, f.transpose(1, 2)) / (c * h * w)


class VGGFeat(torch.nn.Module):
    # 取 relu2_2 与 relu3_3
    def __init__(self):
        super().__init__()
        f = models.vgg16(weights=models.VGG16_Weights.IMAGENET1K_V1).features[:16].eval()
        for p in f.parameters():
            p.requires_grad_(False)
        self.f = f
        self.register_buffer("mean", torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1))
        self.register_buffer("std", torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1))

    def forward(self, x):
        x = (x - self.mean) / self.std
        out = []
        for i, m in enumerate(self.f):
            x = m(x)
            if i in (8, 15):
                out.append(x)
        return out


def save_ckpt(path, net, styles, opt, sched, it, args):
    # 先写临时文件再改名，进程中断时不会留下损坏的检查点
    tmp = path + ".tmp"
    torch.save(dict(cfg=net.cfg, styles=styles, sd=net.state_dict(), qat=QCfg.enabled,
                    it=it, opt=opt.state_dict(), sched=sched.state_dict(), args=vars(args)), tmp)
    os.replace(tmp, path)


def restore(path, net, styles, opt, sched, args):
    # 续训：恢复权重、激活量程、优化器与学习率调度；返回已完成步数
    ck = torch.load(path, map_location="cpu", weights_only=False)
    if ck["cfg"] != net.cfg:
        raise SystemExit(f"网络配置不一致：检查点 {ck['cfg']}，当前 {net.cfg}")
    if ck["styles"] != styles:
        raise SystemExit(f"风格列表不一致：检查点 {ck['styles']}，当前 {styles}")
    old = ck.get("args")
    if old and old.get("iters") != args.iters:
        raise SystemExit(f"--iters 与原训练不一致（原 {old['iters']}），学习率调度会错位")
    net.load_state_dict(ck["sd"])
    it = ck.get("it", args.start_it)
    if it is None or it < 0:
        raise SystemExit("检查点未记录步数，请用 --start_it 指定")
    if "opt" in ck:
        opt.load_state_dict(ck["opt"])
        sched.load_state_dict(ck["sched"])
        note = "权重、优化器、学习率调度全部恢复"
    else:
        # 旧格式检查点只有权重：Adam 动量重新初始化，学习率调度快进到第 it 步
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            for _ in range(it):
                sched.step()
        note = "旧检查点无优化器状态，Adam 动量重新初始化，学习率调度已快进"
    return it, note


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--styles", default="candy,mosaic,rain_princess,udnie")
    ap.add_argument("--C", type=int, default=32)
    ap.add_argument("--Fc", type=int, default=16)
    ap.add_argument("--n_res", type=int, default=3)
    ap.add_argument("--norm", default="in", choices=["in", "bn"])
    ap.add_argument("--block", default="dw2", choices=["dw1", "dw2"])
    ap.add_argument("--iters", type=int, default=20000)
    ap.add_argument("--qat_frac", type=float, default=0.7)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--crop", type=int, default=256)
    ap.add_argument("--lr", type=float, default=2e-3)
    ap.add_argument("--w_pix", type=float, default=1.0)
    ap.add_argument("--w_perc", type=float, default=0.05)
    ap.add_argument("--w_gram", type=float, default=0.0)
    ap.add_argument("--camera_aug_prob", type=float, default=0.0,
                    help="training-only mild exposure/white-balance/gamma/noise augmentation")
    ap.add_argument("--temporal_weight", type=float, default=0.0,
                    help="training-only translated-pair consistency loss; 0 disables it")
    ap.add_argument("--temporal_shift", type=int, default=2,
                    help="maximum synthetic pixel translation used by temporal loss")
    ap.add_argument("--seed", type=int, default=20261003)
    ap.add_argument("--out", default="runs/default")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--save_every", type=int, default=1000)
    ap.add_argument("--resume", default="", help="检查点路径；auto 表示 <out>/student.pt")
    ap.add_argument("--weights_only", default="",
                    help="只加载已有 student.pt 的权重/量程，重新开始一个低学习率微调阶段")
    ap.add_argument("--start_it", type=int, default=-1, help="旧格式检查点（未记录步数）的已完成步数")
    ap.add_argument("--dry_run", action="store_true", help="只检查续训能否恢复，不训练")
    a = ap.parse_args()

    # The deployed StyleCam graph is C24/Fc16/dw1/IN with four residual
    # blocks.  Other values are allowed only for explicitly named offline
    # experiments; this guard prevents an accidental run from overwriting a
    # deployment checkpoint with an incompatible graph.
    if a.out in ("runs/c24_dw1_in", "runs/c24_gram"):
        expected = dict(C=24, Fc=16, n_res=4, block="dw1", norm="in")
        actual = dict(C=a.C, Fc=a.Fc, n_res=a.n_res, block=a.block, norm=a.norm)
        if actual != expected:
            raise SystemExit(f"部署目录 {a.out} 只允许 C24/Fc16/n_res4/dw1/IN；实际 {actual}")
    set_seed(a.seed)

    dev = "cuda"
    torch.backends.cudnn.benchmark = True
    out = os.path.join(ROOT, a.out)
    os.makedirs(out, exist_ok=True)
    ck_path = os.path.join(out, "student.pt")
    logf = open(os.path.join(out, "train.log"), "a", encoding="utf-8")

    def log(msg):
        print(msg, flush=True)
        logf.write(msg + "\n")
        logf.flush()

    styles = a.styles.split(",")
    if a.resume and a.weights_only:
        raise SystemExit("--resume 与 --weights_only 不能同时使用")
    net = TinyStyleNet(a.C, a.Fc, a.n_res, len(styles), a.norm, a.block).to(dev)
    opt = torch.optim.Adam(net.parameters(), lr=a.lr)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, a.lr, total_steps=a.iters, pct_start=0.05)
    qat_at, freeze_at = int(a.iters * a.qat_frac), int(a.iters * 0.9)

    it = 0
    if a.resume:
        rpath = ck_path if a.resume == "auto" else os.path.join(ROOT, a.resume)
        it, note = restore(rpath, net, styles, opt, sched, a)
        QCfg.enabled = it >= qat_at
        QCfg.observe = it < freeze_at
        log(f"== 续训：{rpath} 第 {it}/{a.iters} 步；{note}；"
            f"QAT={'开' if QCfg.enabled else '关'}，量程观测={'开' if QCfg.observe else '冻结'}，"
            f"下一步学习率 {sched.get_last_lr()[0]:.3e}")
    if a.weights_only:
        wpath = a.weights_only if os.path.isabs(a.weights_only) else os.path.join(ROOT, a.weights_only)
        ck = torch.load(wpath, map_location="cpu", weights_only=False)
        if ck.get("cfg") != net.cfg:
            raise SystemExit(f"权重配置不一致：检查点 {ck.get('cfg')}，当前 {net.cfg}")
        if ck.get("styles") != styles:
            raise SystemExit(f"权重风格列表不一致：检查点 {ck.get('styles')}，当前 {styles}")
        net.load_state_dict(ck["sd"])
        it = 0
        # A fresh fine-tune starts in FP32 when qat_frac=1.0 and enables
        # pseudo-quantisation at the requested fraction of this stage.
        QCfg.enabled = a.qat_frac <= 0
        QCfg.observe = True
        log(f"== 权重微调阶段：{wpath}；重置优化器/调度器；总步数 {a.iters}；"
            f"QAT={'开' if QCfg.enabled else '按比例开启'}")
    if a.dry_run:
        return

    macs, _ = macs_per_pixel(net.specs)
    w, aff, b = param_count(net.specs, len(styles))
    lb, sk = buffer_bytes(net.specs)
    info = dict(vars(a), macs_per_px=macs, weights=w, affine=aff, bias=b, linebuf_B=lb, skipfifo_B=sk)
    log(json.dumps(info, ensure_ascii=False))
    if not a.resume:
        json.dump(info, open(os.path.join(out, "config.json"), "w"), ensure_ascii=False, indent=1)

    teachers = [load_teacher(os.path.join(DATA, "saved_models", f"{s}.pth"), dev) for s in styles]
    vgg = VGGFeat().to(dev)
    train_files, _ = image_list()
    dl = DataLoader(CropSet(train_files, a.crop), batch_size=a.batch, shuffle=True,
                    num_workers=a.workers, drop_last=True,
                    persistent_workers=(a.workers > 0))

    t0, acc = time.time(), [0.0, 0.0]
    while it < a.iters:
        for xb in dl:
            if it == qat_at:
                QCfg.enabled = True
                log("== QAT on")
            if it == freeze_at:
                QCfg.observe = False
                log("== 激活量程冻结")
            si = it % len(styles)
            x = xb.to(dev, non_blocking=True).float()
            if a.camera_aug_prob > 0:
                x = camera_domain_augment(x, a.camera_aug_prob)
            with torch.no_grad(), torch.autocast("cuda", dtype=torch.float16):
                tgt = (teachers[si](x).float().clamp(0, 255) / 255.0)
                ft = vgg(tgt)
            style = torch.full((x.shape[0],), si, dtype=torch.long, device=dev)
            y = net(x / 255.0, style)
            with torch.autocast("cuda", dtype=torch.float16):
                fy = vgg(y)
            l_pix = F.l1_loss(y, tgt)
            l_perc = sum(F.mse_loss(p.float(), q.float()) for p, q in zip(fy, ft))
            loss = a.w_pix * l_pix + a.w_perc * l_perc
            if a.w_gram > 0:
                # 纹理（Gram）损失：只约束特征二阶统计，不要求笔触位置逐像素一致
                l_gram = sum(F.mse_loss(gram(p.float()), gram(q.float())) for p, q in zip(fy, ft))
                loss = loss + a.w_gram * l_gram
            if a.temporal_weight > 0 and a.temporal_shift > 0:
                x_pair, sl = temporal_shift_pair(x, a.temporal_shift)
                y_pair = net(x_pair / 255.0, style)
                y0 = y[:, :, sl[2], sl[3]]
                y1 = y_pair[:, :, sl[0], sl[1]]
                l_temporal = 0.5 * (F.smooth_l1_loss(y1, y0.detach()) +
                                    F.smooth_l1_loss(y0, y1.detach()))
                loss = loss + a.temporal_weight * l_temporal
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(net.parameters(), 1.0)
            opt.step()
            sched.step()
            acc[0] += l_pix.item()
            acc[1] += l_perc.item()
            it += 1
            if it % 200 == 0:
                log(f"it {it} pix {acc[0]/200:.4f} perc {acc[1]/200:.4f} "
                    f"lr {sched.get_last_lr()[0]:.2e} {time.time()-t0:.0f}s")
                acc = [0.0, 0.0]
            if it % a.save_every == 0 or it == a.iters:
                save_ckpt(ck_path, net, styles, opt, sched, it, a)
            if it >= a.iters:
                break
    log(f"done {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()

