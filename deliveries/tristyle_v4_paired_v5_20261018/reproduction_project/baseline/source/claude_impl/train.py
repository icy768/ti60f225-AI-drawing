"""Claude v3 trainer: paired per-style targets + VGG perceptual/texture + high-frequency
matching + real-video (Sintel train pairs) flow-warp temporal loss.
Stages: joint skeleton -> per-expert strengthening (shared frozen) -> balanced joint refine.
"""
import sys, os, json, time, random, argparse, pathlib, hashlib, shutil, platform
import numpy as np, torch
from torch import nn
from torch.nn import functional as F
from PIL import Image, ImageDraw
HERE = pathlib.Path(__file__).resolve().parent; ROOT = HERE.parent
sys.path.insert(0, str(HERE)); sys.path.insert(1, str(ROOT))
from model import TriStyleV3, STYLES, size_report

TGT = ROOT / 'data/claude_targets'

TARGET_DIRS = list(STYLES)  # overridable via --targets (e.g. vangogh,ukiyoe2,ink2)

class Paired(torch.utils.data.Dataset):
    def __init__(self, split, size=256, dirs=None):
        self.dirs = dirs or TARGET_DIRS
        self.stems = sorted(p.stem for p in (TGT / 'content' / split).glob('*.png')
                            if all((TGT / s / split / p.name).exists() for s in self.dirs))
        self.split, self.size = split, size
    def __len__(self): return len(self.stems)
    def __getitem__(self, i):
        ims = [np.array(Image.open(TGT / s / self.split / (self.stems[i] + '.png')).convert('RGB')) for s in ['content'] + list(self.dirs)]
        h, w = ims[0].shape[:2]; s = self.size
        if self.split == 'train':
            t, l = random.randrange(h - s + 1), random.randrange(w - s + 1)
        else:
            t, l = (h - s) // 2, (w - s) // 2
        ims = [a[t:t + s, l:l + s] for a in ims]
        if self.split == 'train' and random.random() < .5: ims = [a[:, ::-1] for a in ims]
        return torch.from_numpy(np.ascontiguousarray(np.stack(ims))).permute(0, 3, 1, 2).float() / 255

class VGG(nn.Module):
    def __init__(self):
        super().__init__()
        from torchvision.models import vgg16
        net = vgg16(weights=None); net.load_state_dict(torch.load(ROOT / 'teachers/weights/vgg16.pth', map_location='cpu', weights_only=True))
        self.f = net.features[:23].eval()
        for p in self.f.parameters(): p.requires_grad_(False)
        self.register_buffer('m', torch.tensor([.485, .456, .406]).view(1, 3, 1, 1)); self.register_buffer('s', torch.tensor([.229, .224, .225]).view(1, 3, 1, 1))
    def forward(self, x):
        x = (x - self.m) / self.s; out = []
        for i, m in enumerate(self.f):
            x = m(x)
            if i in (3, 8, 15, 22): out.append(x)
        return out

def gram(f):
    with torch.autocast('cuda', enabled=False):
        n, c, h, w = f.shape; f = f.float().reshape(n, c, h * w) / (h * w) ** .5; return f @ f.transpose(1, 2) / c

def highpass(x):
    return x - F.avg_pool2d(F.pad(x, (2, 2, 2, 2), mode='reflect'), 5, 1)

_OK = {}
def oriented_kernels(dev):
    """Second-derivative-of-Gaussian band-pass at 4 orientations x 2 scales (fixed, not learned)."""
    if dev in _OK: return _OK[dev]
    ks = []
    for sig in (1.5, 3.0):
        r = int(3 * sig); yy, xx = torch.meshgrid(torch.arange(-r, r + 1.), torch.arange(-r, r + 1.), indexing='ij')
        for th in (0, 45, 90, 135):
            c, s_ = np.cos(np.radians(th)), np.sin(np.radians(th)); u = xx * c + yy * s_; v = -xx * s_ + yy * c
            g = torch.exp(-(u ** 2 / (2 * sig ** 2) + v ** 2 / (2 * (2.5 * sig) ** 2)))  # elongated along stroke
            k = (u ** 2 / sig ** 4 - 1 / sig ** 2) * g; k = k - k.mean(); k = k / k.abs().sum()
            ks.append(F.pad(k, ((9 - r), (9 - r), (9 - r), (9 - r))))
    K = torch.stack(ks)[:, None].to(dev); _OK[dev] = K; return K

def oriented_energy(x):
    g = (x * torch.tensor([.299, .587, .114], device=x.device).view(1, 3, 1, 1)).sum(1, keepdim=True)
    with torch.autocast('cuda', enabled=False):
        r = F.conv2d(F.pad(g.float(), (9, 9, 9, 9), mode='reflect'), oriented_kernels(x.device))
        return (F.avg_pool2d(r * r, 9, 1, 4) + 1e-6).sqrt()  # phase-invariant local oriented energy

def style_loss(y, t, fy, ft, w):
    pix = F.l1_loss(y, t)
    low = F.l1_loss(F.avg_pool2d(y, 8), F.avg_pool2d(t, 8))
    hf = F.l1_loss(highpass(y), highpass(t))
    perc = sum(F.l1_loss(a.float(), b.float()) * k for a, b, k in zip(fy, ft, (1., 1., 1., 1.)))
    # windowed Gram on 64px tiles: texture statistics, locally, never one global Gram
    tex = 0.
    for a, b in zip(fy[:3], ft[:3]):
        n, c, h, w_ = a.shape; g = max(1, h // 4)
        ua = a.unfold(2, g, g).unfold(3, g, g).permute(0, 2, 3, 1, 4, 5).reshape(-1, c, g, g)
        ub = b.unfold(2, g, g).unfold(3, g, g).permute(0, 2, 3, 1, 4, 5).reshape(-1, c, g, g)
        tex = tex + F.l1_loss(gram(ua), gram(ub))
    orient = F.l1_loss(oriented_energy(y), oriented_energy(t)) if w.get('orient', 0) > 0 else y.new_zeros(())
    terms = {'pix': pix, 'low': low, 'hf': hf, 'perc': perc, 'tex': tex, 'orient': orient}
    return sum(terms[k] * w.get(k, 0.) for k in terms), terms

WEIGHTS = {  # per style; ink/ukiyoe targets are crisp line/flat images -> higher pixel/hf weight
    'vangogh': {'pix': 1.0, 'low': 1.0, 'hf': 2.0, 'perc': 0.10, 'tex': 150.},
    'ukiyoe': {'pix': 2.0, 'low': 1.0, 'hf': 3.0, 'perc': 0.06, 'tex': 60.},
    'ink': {'pix': 2.0, 'low': 1.0, 'hf': 3.0, 'perc': 0.06, 'tex': 60.},
}

class Video:
    def __init__(self):
        self.files = sorted((ROOT / 'data/video/train_pairs').glob('*.npz'))
        self.cache = {}
    def batch(self, n, dev):
        A, B, G = [], [], []
        for f in random.sample(self.files, n):
            if f not in self.cache:
                d = np.load(f); self.cache[f] = (d['a'].copy(), d['b'].copy(), d['backward'].copy())
            a, b, fl = self.cache[f]; h, w = fl.shape[:2]
            gy, gx = np.mgrid[:h, :w].astype(np.float32)
            G.append(np.stack([(gx + fl[..., 0]) * 2 / (w - 1) - 1, (gy + fl[..., 1]) * 2 / (h - 1) - 1], -1)); A.append(a); B.append(b)
        t = lambda L: torch.from_numpy(np.stack(L)).permute(0, 3, 1, 2).float().to(dev) / 255
        return t(A), t(B), torch.from_numpy(np.stack(G)).to(dev)

def temporal_loss(model, vid, dev, n=2, experts=(0, 1, 2)):
    a, b, grid = vid.batch(n, dev)
    with torch.no_grad():
        wa = F.grid_sample(a, grid, align_corners=True)
        mask = ((wa - b).abs().mean(1, keepdim=True) < .08).float() * (grid.abs() < .98).all(-1).unsqueeze(1).float()
    fa, fb = model.encode(a), model.encode(b); loss = 0.
    for i in experts:
        ya = model.experts[i](*fa); yb = model.experts[i](*fb)
        wy = F.grid_sample(ya.float(), grid, align_corners=True)
        loss = loss + ((yb.float() - wy).abs() * mask).sum() / (mask.sum() * 3 + 1)
    return loss

def save_grid(rows, dest, W=320, H=240):
    c = Image.new('RGB', (W * 4, (H + 16) * len(rows)), 'white'); d = ImageDraw.Draw(c)
    for i, (name, ims) in enumerate(rows):
        for j, im in enumerate(ims):
            p = Image.fromarray(im); p.thumbnail((W, H)); c.paste(p, (j * W, i * (H + 16)))
            d.text((j * W + 3, i * (H + 16) + H + 2), f'{name} {["input", *STYLES][j]}', fill='black')
    dest.parent.mkdir(parents=True, exist_ok=True); c.save(dest, quality=88)

@torch.no_grad()
def gallery(model, dest, dev):
    """All 17 fixed test scenes at native size (<=640 wide), three styles."""
    was = model.training; model.eval(); rows = []
    for f in sorted((ROOT / 'data/test').glob('*.png')):
        im = Image.open(f).convert('RGB'); im = im.crop((0, 0, im.width // 8 * 8, im.height // 8 * 8))
        a = np.array(im); x = torch.from_numpy(a).permute(2, 0, 1)[None].float().to(dev) / 255
        ys = [(model(x, s)[0].clamp(0, 1).permute(1, 2, 0).cpu().numpy() * 255).round().astype(np.uint8) for s in range(3)]
        for s, y in enumerate(ys): Image.fromarray(y).save(dest / f'{f.stem}_{STYLES[s]}.png')
        rows.append((f.stem, [a] + ys))
    save_grid(rows, dest / 'comparison.jpg'); model.train(was)

def status(run, **kw):
    p = ROOT / 'supervisor/claude_status.json'
    try: st = json.loads(p.read_text(encoding='utf-8'))
    except Exception: st = {}
    st.update(kw); st['time'] = time.strftime('%Y-%m-%dT%H:%M:%S+08:00'); st['run'] = run; st['pid'] = os.getpid()
    p.write_text(json.dumps(st, indent=1, ensure_ascii=False), encoding='utf-8')

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run', required=True); ap.add_argument('--steps', type=int, default=30000)
    ap.add_argument('--batch', type=int, default=6); ap.add_argument('--size', type=int, default=256)
    ap.add_argument('--joint1', type=int, default=4000); ap.add_argument('--special', type=int, default=12000)
    ap.add_argument('--lr', type=float, default=1e-3); ap.add_argument('--eval-every', type=int, default=1000)
    ap.add_argument('--temporal', type=float, default=1.0); ap.add_argument('--seed', type=int, default=20261017)
    ap.add_argument('--init', default=''); ap.add_argument('--targets', default='vangogh,ukiyoe,ink'); ap.add_argument('--weights', default=''); ap.add_argument('--workers', type=int, default=3); ap.add_argument('--only-expert', type=int, default=-1); ap.add_argument('--resume', default='')
    a = ap.parse_args()
    if a.weights:
        for k, v in json.loads(a.weights).items(): WEIGHTS[k].update(v)
    random.seed(a.seed); np.random.seed(a.seed); torch.manual_seed(a.seed); torch.set_num_threads(4)
    torch.backends.cudnn.benchmark = True; dev = 'cuda'
    out = ROOT / 'runs' / a.run; out.mkdir(parents=True, exist_ok=True)
    src = out / 'source'; src.mkdir(exist_ok=True)
    for p in HERE.glob('*.py'): shutil.copy2(p, src / p.name)
    (out / 'config.json').write_text(json.dumps(vars(a), indent=1))
    (out / 'provenance.json').write_text(json.dumps({'source_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in src.glob('*.py')},
        'python': platform.python_version(), 'torch': torch.__version__, 'device': torch.cuda.get_device_name(), 'seed': a.seed,
        'size_report': size_report(), 'targets': 'data/claude_targets (claude_impl/precompute.py, deterministic)',
        'determinism': 'cudnn.benchmark on; bit-exact replay not guaranteed'}, indent=1))
    dirs = a.targets.split(','); ds = Paired('train', a.size, dirs); vd = Paired('validation', a.size, dirs)
    dl = torch.utils.data.DataLoader(ds, a.batch, shuffle=True, num_workers=a.workers, drop_last=True, persistent_workers=a.workers > 0)
    model = TriStyleV3().to(dev).train(); vgg = VGG().to(dev); vid = Video()
    opt = torch.optim.Adam(model.parameters(), a.lr, betas=(.9, .99)); step0 = 0
    if a.init: model.load_state_dict(torch.load(a.init, map_location='cpu', weights_only=False)['model'])
    if a.resume:
        sd = torch.load(a.resume, map_location='cpu', weights_only=False); model.load_state_dict(sd['model']); opt.load_state_dict(sd['opt']); step0 = sd['step']
    scaler = torch.amp.GradScaler('cuda'); log = (out / 'metrics.jsonl').open('a', buffering=1)
    shared = [p for n, p in model.named_parameters() if not n.startswith('experts.')]
    it = iter(dl); t0 = time.time(); stage = None
    status(a.run, stage='training_start', step=step0, log=str((out / 'train.log').relative_to(ROOT)), failures=[])
    for step in range(step0 + 1, a.steps + 1):
        if (out / 'STOP').exists(): break
        try: b = next(it)
        except StopIteration: it = iter(dl); b = next(it)
        b = b.to(dev, non_blocking=True); x = b[:, 0]; tg = [b[:, 1 + i] for i in range(3)]
        st = 'joint_skeleton' if step <= a.joint1 else 'expert_strengthen' if step <= a.joint1 + a.special else 'joint_refine'
        if a.only_expert >= 0: st = 'single_expert_%d' % a.only_expert
        if st != stage:
            for p in shared: p.requires_grad_(st not in ('expert_strengthen',) and not st.startswith('single_expert'))
            if st.startswith('single_expert'):
                for i, e in enumerate(model.experts):
                    for p in e.parameters(): p.requires_grad_(i == a.only_expert)
            stage = st; print('STAGE', st, step, flush=True)
        # cosine within stage
        T = a.steps
        lr = a.lr * (0.5 * (1 + np.cos(np.pi * min(1., step / T))) * 0.9 + 0.1)
        if st == 'joint_refine': lr *= 0.5
        for g in opt.param_groups: g['lr'] = lr
        opt.zero_grad(set_to_none=True)
        with torch.autocast('cuda', torch.float16):
            if st == 'expert_strengthen' or st.startswith('single_expert'):
                # one expert per step, stronger focus; shared encoder frozen
                ei = a.only_expert if a.only_expert >= 0 else (step - a.joint1 - 1) % 3; experts = [ei]
                with torch.no_grad(): f = model.encode(x)
                ys = {ei: model.experts[ei](*f)}
            else:
                experts = [0, 1, 2]; ys = dict(enumerate(model.forward_all(x)))
            loss = 0.; terms = {}
            for i in experts:
                y = ys[i].float().clamp(0, 1) * 0.98 + ys[i].float() * 0.02  # leak avoids dead clamp gradients
                fy = vgg(y);
                with torch.no_grad(): ft = vgg(tg[i])
                l, tm = style_loss(y, tg[i], fy, ft, WEIGHTS[STYLES[i]]); loss = loss + l
                terms.update({f'{STYLES[i]}_{k}': float(v) for k, v in tm.items()})
            if a.temporal > 0 and step % 2 == 0:
                tl = temporal_loss(model, vid, dev, 2, experts); loss = loss + a.temporal * tl; terms['temporal'] = float(tl)
        if not torch.isfinite(loss): raise FloatingPointError('nonfinite loss at %d' % step)
        scaler.scale(loss).backward(); scaler.unscale_(opt); nn.utils.clip_grad_norm_(model.parameters(), 2.); scaler.step(opt); scaler.update()
        if step % 20 == 0:
            log.write(json.dumps({'step': step, 'stage': st, 'lr': lr, 'loss': float(loss), 'terms': terms, 'sec': time.time() - t0}) + '\n')
        if step % 100 == 0:
            print(f'STEP {step} {st} loss {float(loss):.4f} {(time.time() - t0) / (step - step0):.3f}s/step', flush=True)
        if step % 500 == 0:
            torch.save({'model': model.state_dict(), 'opt': opt.state_dict(), 'step': step, 'stage': st, 'config': vars(a)}, out / 'latest.pt')
        if step % a.eval_every == 0 or step == a.steps:
            ck = out / f'step_{step:06d}.pt'; torch.save({'model': model.state_dict(), 'step': step, 'stage': st, 'config': vars(a)}, ck)
            dest = ROOT / 'reports/claude/progress' / a.run / f'{step:06d}'; dest.mkdir(parents=True, exist_ok=True); gallery(model, dest, dev)
            # validation: per-style target distance (proxy only; NOT artistic acceptance)
            model.eval(); vl = {}
            with torch.no_grad():
                vb = torch.stack([vd[i] for i in range(0, len(vd), 8)]).to(dev); outs = model.forward_all(vb[:, 0])
                for i, s in enumerate(STYLES): vl[s] = float(F.l1_loss(outs[i].clamp(0, 1), vb[:, 1 + i]))
            model.train()
            log.write(json.dumps({'step': step, 'val_l1_to_target': vl, 'checkpoint': str(ck.relative_to(ROOT)), 'gallery': str((dest / 'comparison.jpg').relative_to(ROOT))}) + '\n')
            print('EVAL', step, vl, flush=True)
            status(a.run, stage=st, step=step, checkpoint=str(ck.relative_to(ROOT)), comparison_path=str((dest / 'comparison.jpg').relative_to(ROOT)), val_l1_to_target_proxy=vl)
    torch.save({'model': model.state_dict(), 'opt': opt.state_dict(), 'step': step, 'stage': stage, 'config': vars(a)}, out / 'latest.pt')
    (out / 'finished.json').write_text(json.dumps({'step': step, 'elapsed_sec': time.time() - t0}))
    print('FINISHED', step, flush=True)

if __name__ == '__main__':
    main()
