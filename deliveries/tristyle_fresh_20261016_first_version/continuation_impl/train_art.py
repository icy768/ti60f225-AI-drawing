"""Authorized Codex continuation after CC provider restoration failed, 2026-10-17.

Retains this project's v3 deployable topology. Real public-domain artwork patches
guide texture; current paired targets only anchor coarse layout/flow. No test image
or heldout video is optimized. Inference remains the bare neural network.
"""
import argparse, datetime, hashlib, json, pathlib, random, shutil, sys, time
import numpy as np
import torch
from torch.nn import functional as F
from PIL import Image

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'claude_impl'))
from model import TriStyleV3, STYLES, model_for_state
from train import Paired, VGG, Video, gallery, temporal_loss, oriented_energy
from data import reference_paths, reference_crop


class StyleCritic(torch.nn.Module):
    """Training-only local artwork critic; never included in a student deployment pack."""
    def __init__(self, texture=False):
        super().__init__(); self.texture = texture; layers = []; cin = 3
        for cout, kernel, stride in ((24, 5, 2), (48, 4, 2), (96, 4, 2), (128, 4, 2)):
            layers += [torch.nn.utils.spectral_norm(torch.nn.Conv2d(cin, cout, kernel, stride, 1)), torch.nn.LeakyReLU(.2)]
            cin = cout
        layers.append(torch.nn.utils.spectral_norm(torch.nn.Conv2d(cin, 1, 3, 1, 1)))
        self.net = torch.nn.Sequential(*layers)
    def forward(self, x):
        if not self.texture: return self.net(x * 2 - 1)
        g = (x * x.new_tensor([.299, .587, .114]).view(1, 3, 1, 1)).sum(1, keepdim=True)
        bands = []
        for k in (3, 9, 21):
            mu = F.avg_pool2d(F.pad(g, (k // 2,) * 4, mode='reflect'), k, 1)
            hp = g - mu
            sd = (F.avg_pool2d(F.pad(hp * hp, (7,) * 4, mode='reflect'), 15, 1) + .0002).sqrt()
            bands.append(torch.tanh(hp / (sd + .015)))
        return self.net(torch.cat(bands, 1))


def constrain_content_routes(model, stems, size, dev, suppress=False):
    factors = [(0.45, .25, .08), (.55, .30, .10), (.65, .45, .18)]
    means, counts, hooks = {}, {}, []
    if suppress:
        for i, expert in enumerate(model.experts):
            for stage, skip in (('s4', 64), ('s2', 32), ('s1', 16)):
                mod = getattr(expert, stage).fuse.conv; key = f'experts.{i}.{stage}'
                def hook(m, args, output, k=key, nskip=skip):
                    response = F.conv2d(args[0][:, -nskip:], m.weight[:, -nskip:]).mean((0, 2, 3))
                    means[k] = means.get(k, torch.zeros_like(response)) + response
                    counts[k] = counts.get(k, 0) + 1
                hooks.append(mod.register_forward_hook(hook))
        model.eval()
        with torch.no_grad():
            for stem in stems[:16]:
                im = Image.open(ROOT / 'data/claude_targets/content/train' / (stem + '.png')).convert('RGB')
                l, t = (im.width - size) // 2, (im.height - size) // 2
                arr = np.array(im.crop((l, t, l + size, t + size)), copy=True)
                x = torch.from_numpy(arr).permute(2, 0, 1)[None].float().to(dev) / 255
                for i in range(3): model(x, i)
        for h in hooks: h.remove()
    for i, expert in enumerate(model.experts):
        for (stage, skip), factor in zip((('s4', 64), ('s2', 32), ('s1', 16)), factors[i]):
            mod = getattr(expert, stage).fuse.conv; key = f'experts.{i}.{stage}'
            if suppress:
                with torch.no_grad():
                    mod.bias.add_((1 - factor) * means[key] / counts[key]); mod.weight[:, -skip:].mul_(factor)
            mask = torch.ones_like(mod.weight); mask[:, -skip:] = 0
            mod.weight.register_hook(lambda grad, m=mask: grad * m)
    return {'factors_s4_s2_s1': factors, 'calibration_stems': stems[:16] if suppress else [],
            'bias_compensation': 'mean skip contribution from deterministic centered TRAINING crops; folded into biases',
            'runtime': 'no new op/parameter; gate folded into existing fuse weights; skip slices frozen during this training run'}


class SpatialPaired(Paired):
    """Aligned image/target/head-mask crops. Masks supervise training; RGB is the only network input."""
    def __getitem__(self, i):
        p = self.stems[i] + '.png'
        ims = [np.array(Image.open(ROOT / 'data/claude_targets' / s / self.split / p).convert('RGB'), copy=True)
               for s in ['content'] + list(self.dirs)]
        mp = ROOT / 'data/claude_targets/content_masks' / self.split / p
        mask = np.array(Image.open(mp).convert('L'), copy=True) if mp.exists() else np.zeros(ims[0].shape[:2], np.uint8)
        ims.append(np.repeat(mask[..., None], 3, axis=2))
        h, w = mask.shape; size = self.size
        t, l = (random.randrange(h - size + 1), random.randrange(w - size + 1)) if self.split == 'train' else ((h - size) // 2, (w - size) // 2)
        ims = [z[t:t + size, l:l + size] for z in ims]
        if self.split == 'train' and random.random() < .5: ims = [z[:, ::-1] for z in ims]
        return torch.from_numpy(np.ascontiguousarray(np.stack(ims))).permute(0, 3, 1, 2).float() / 255


def descriptors(f, count=256):
    # Local 3x3 feature neighborhoods, no pixel-aligned reference supervision.
    u = F.unfold(f.float(), 3, padding=1, stride=2).transpose(1, 2)
    if u.shape[1] > count:
        ids = torch.randperm(u.shape[1], device=f.device)[:count]
        u = u[:, ids]
    return u


def standardized(f):
    return (f - f.mean((2, 3), keepdim=True)) / (f.var((2, 3), keepdim=True, unbiased=False) + 0.05).sqrt()


def centered(d):
    z = d.reshape(*d.shape[:-1], -1, 9)
    return (z - z.mean(-1, keepdim=True)).flatten(-2)


def brush_direction_loss(y, target, content):
    # Remove the input's explainable fine edges; compare direction distributions
    # of the remaining brush field, not aligned pixels or only total energy.
    hp = lambda z: z - F.avg_pool2d(F.pad(z, (2, 2, 2, 2), mode='reflect'), 5, 1)
    xc, tc, yc = hp(content.float()), hp(target.float()), hp(y.float())
    with torch.no_grad():
        k = ((tc * xc).mean((1, 2, 3), keepdim=True) / (xc.square().mean((1, 2, 3), keepdim=True) + 1e-5)).clamp(0, 2)
        et = oriented_energy(tc - k * xc).reshape(y.shape[0], 2, 4, *y.shape[-2:])
        pt = et / (et.sum(2, keepdim=True) + 1e-5)
        confidence = (et.sum(2, keepdim=True) / .02).clamp(.1, 1)
    ey = oriented_energy(yc - k * xc).reshape(y.shape[0], 2, 4, *y.shape[-2:])
    py = ey / (ey.sum(2, keepdim=True) + 1e-5)
    angular = ((py - pt).abs() * confidence).mean()
    continuity = (py[..., 1:, :] - py[..., :-1, :]).abs().mean() + (py[..., :, 1:] - py[..., :, :-1]).abs().mean()
    return angular + .5 * continuity


class ArtBank:
    def __init__(self, vgg, dev):
        self.bank = {}
        self.refs = {}
        for style in STYLES:
            paths = reference_paths(style)
            if style == 'vangogh':
                paths = [p for p in paths if p.stem in ('starry_night', '436532', '436534', '436535')]
            if style == 'ink':
                paths = [p for p in paths if p.stem in ('45683', '49179', '49180', '51856', '51858', '49170', '39556')]
            # Fixed deterministic reference crops, identity/hash recorded.
            paths = paths[:8]
            assert paths, style
            self.refs[style] = [{'path': str(p.relative_to(ROOT)), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths]
            patches = [[], []]
            means, stds = [[], [], []], [[], [], []]
            for p in paths:
                im = Image.open(p).convert('RGB'); w, h = im.size
                if style == 'ink' and h > w * 2:
                    im = im.crop((int(w * .12), int(h * .05), int(w * .88), int(h * .95)))
                scale = 320 / min(im.size)
                im = im.resize((round(im.width * scale), round(im.height * scale)), Image.Resampling.LANCZOS)
                for pos in (.25, .65):
                    l = round((im.width - 256) * pos); t = round((im.height - 256) * pos)
                    a = np.array(im.crop((l, t, l + 256, t + 256)), copy=True)
                    x = torch.from_numpy(a).permute(2, 0, 1)[None].float().to(dev) / 255
                    with torch.no_grad(), torch.autocast('cuda', enabled=dev == 'cuda'):
                        fs = vgg(x)
                    for j in range(2):
                        d = descriptors(fs[j + 1], 1024)[0].detach()
                        dc = centered(d)
                        ids = dc.square().mean(-1).topk(min(80, d.shape[0])).indices
                        patches[j].append(dc[ids])
                    for j in range(3):
                        means[j].append(fs[j].float().mean((2, 3))[0]); stds[j].append(fs[j].float().std((2, 3), unbiased=False)[0])
            self.bank[style] = {
                'patches': [torch.cat(z) for z in patches],
                'mean': [torch.stack(z).mean(0) for z in means],
                'std': [torch.stack(z).mean(0) for z in stds],
            }
            print('BANK', style, [list(v.shape) for v in self.bank[style]['patches']], flush=True)

    def losses(self, fs, style):
        b = self.bank[style]; patch = fs[0].new_zeros((), dtype=torch.float32)
        for j in range(2):
            u = centered(descriptors(fs[j + 1])); r = b['patches'][j]
            with torch.no_grad():
                # Normalized matching selects brush neighborhoods independent of phase.
                ids = (F.normalize(u.detach(), dim=-1) @ F.normalize(r, dim=-1).T).argmax(-1)
                target = r[ids]
            patch = patch + F.smooth_l1_loss(u, target)
        moment = patch.new_zeros(())
        for j in range(3):
            f = fs[j].float()
            moment = moment + F.l1_loss(f.mean((2, 3)), b['mean'][j][None].expand(f.shape[0], -1))
            moment = moment + F.l1_loss(f.std((2, 3), unbiased=False), b['std'][j][None].expand(f.shape[0], -1))
        return patch, moment


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--init', required=True); ap.add_argument('--run', required=True)
    ap.add_argument('--steps', type=int, default=3600); ap.add_argument('--batch', type=int, default=2)
    ap.add_argument('--size', type=int, default=256); ap.add_argument('--lr', type=float, default=1.5e-4)
    ap.add_argument('--eval-every', type=int, default=300); ap.add_argument('--seed', type=int, default=20261017)
    ap.add_argument('--joint-last', type=int, default=600); ap.add_argument('--device', default='cuda')
    ap.add_argument('--patch-scale', type=float, default=1.0)
    ap.add_argument('--targets', default='vangogh5,ukiyoe3,ink5'); ap.add_argument('--full-kernels', default='')
    ap.add_argument('--min-dataset', type=int, default=2)
    ap.add_argument('--replay-data', default='', help='Use the recorded dataset_schedule.jsonl of a previous growing-target run')
    ap.add_argument('--stop-at', default='', help='Optional ISO8601 safety deadline; omitted for later reproduction')
    ap.add_argument('--adversarial-weight', type=float, default=0.)
    ap.add_argument('--critic-texture', action='store_true'); ap.add_argument('--suppress-skips', action='store_true')
    ap.add_argument('--freeze-skip-routes', action='store_true')
    ap.add_argument('--head-edge-weight', type=float, default=0., help='Training-mask normalized luminance edge supervision for fine face features; no inference mask')
    ap.add_argument('--content-multiplier', type=float, default=1.)
    a = ap.parse_args()
    random.seed(a.seed); np.random.seed(a.seed); torch.manual_seed(a.seed); torch.set_num_threads(3)
    torch.backends.cudnn.benchmark = True; dev = a.device
    out = ROOT / 'runs' / a.run; out.mkdir(parents=True, exist_ok=True)
    assert not (out / 'latest.pt').exists(), 'Use a new run name; do not overwrite candidates'
    state = torch.load(ROOT / a.init, map_location='cpu', weights_only=False)['model']
    kernels = list(map(int, a.full_kernels.split(','))) if a.full_kernels else None
    model = (TriStyleV3(kernels) if kernels else model_for_state(state)).to(dev)
    if kernels:
        for i, k in enumerate(kernels):
            key = f'experts.{i}.dw1.conv.weight'; old = state[key].shape[-1]; assert k >= old and (k - old) % 2 == 0
            p = (k - old) // 2; state[key] = F.pad(state[key], (p, p, p, p))
    model.load_state_dict(state, strict=True)
    vgg = VGG().to(dev); bank = ArtBank(vgg, dev); video = Video()
    dirs = a.targets.split(','); assert len(dirs) == 3
    ds_type = SpatialPaired if dirs[0] == 'vangogh_p1' else Paired
    replay = {r['step']: r['stems'] for r in map(json.loads, (ROOT / a.replay_data).read_text().splitlines())} if a.replay_data else {}
    ds = ds_type('train', a.size, dirs)
    if replay:
        available = set(ds.stems); assert all(s in available for seq in replay.values() for s in seq)
        ds.stems = replay[1]
    while len(ds) < max(a.batch, a.min_dataset):
        print('WAIT_DATA', len(ds), 'minimum', a.min_dataset, flush=True); time.sleep(10); ds = ds_type('train', a.size, dirs)
    route_info = constrain_content_routes(model, ds.stems, a.size, dev, suppress=a.suppress_skips) if (a.suppress_skips or a.freeze_skip_routes) else None
    dl = torch.utils.data.DataLoader(ds, a.batch, shuffle=True, num_workers=0, drop_last=True)
    it = iter(dl); opt = torch.optim.Adam(model.parameters(), a.lr, betas=(.9, .99))
    scaler = torch.amp.GradScaler('cuda', enabled=dev == 'cuda')
    critics = torch.nn.ModuleList([StyleCritic(a.critic_texture) for _ in STYLES]).to(dev) if a.adversarial_weight else None
    critic_opts = [torch.optim.Adam(d.parameters(), 1e-4, betas=(0., .99)) for d in critics] if critics is not None else []
    src = out / 'source'; src.mkdir(exist_ok=True)
    for base in (HERE, ROOT / 'claude_impl'):
        dest = src / base.name; dest.mkdir(exist_ok=True)
        for p in base.glob('*.py'): shutil.copy2(p, dest / p.name)
    cfg = {**vars(a), 'targets': dirs, 'reference_bank': bank.refs,
           'full_kernels_actual': [int(e.dw1.conv.kernel_size[0]) for e in model.experts],
           'objective': 'actual artwork local feature patches + moments; content features, coarse paired layout/flow, training-only video temporal',
           'weights': {'patch': [.15, .16, .25], 'moment': [.15, .08, .18], 'pixel': [.4, .40, .35], 'coarse': .75, 'content': [.18, .45, .35], 'orientation': [180, 0, 15], 'brush_direction': [6., 0, 1.5], 'equivariance': [12., 5., 8.]},
           'art_patch_policy': 'center each feature channel within 3x3; reference top80 contrast patches of1024 per crop; NCC nearest matching, contrast reconstruction; separate feature moments for palette',
           'source_checkpoint_sha256': hashlib.sha256((ROOT / a.init).read_bytes()).hexdigest(),
           'source_sha256': {str(p.relative_to(src)): hashlib.sha256(p.read_bytes()).hexdigest() for p in src.rglob('*.py')},
           'bit_exact_replay': 'not guaranteed: CUDA benchmark/AMP; seeds and source preserved'}
    cfg['critic_real_policy'] = 'Equal batches of paired stylized training targets and legal actual-artwork crops; 3 independent local spectral-normalized critics. Training only.' if critics is not None else None
    cfg['content_route_constraint'] = route_info
    if a.suppress_skips: torch.save({'model': model.state_dict(), 'config': cfg, 'step': 0}, out / 'initial_gated.pt')
    (out / 'config.json').write_text(json.dumps(cfg, indent=2), encoding='utf-8')
    if dirs[0] in ('vangogh7', 'vangogh8', 'vangogh_p1'):
        cfg['weights'].update({'pixel': [2., 1.5, 1.5], 'coarse': 1.5, 'content': [.22, .45, .35], 'orientation': [90., 0, 20.],
                               'brush_direction': [4., 0, 2.], 'guide_perceptual': [.08, .06, .08]})
        (out / 'config.json').write_text(json.dumps(cfg, indent=2), encoding='utf-8')
    cfg['weights']['content']=[w*a.content_multiplier for w in cfg['weights']['content']]
    (out / 'config.json').write_text(json.dumps(cfg,indent=2),encoding='utf-8')
    log = (out / 'metrics.jsonl').open('a', buffering=1); start = time.time(); last_step = 0
    deadline = datetime.datetime.fromisoformat(a.stop_at).timestamp() if a.stop_at else float('inf')
    data_schedule = (out / 'dataset_schedule.jsonl').open('a', buffering=1)
    data_schedule.write(json.dumps({'step': 1, 'stems': ds.stems}) + '\n')
    for step in range(1, a.steps + 1):
        if (out / 'STOP').exists() or time.time() >= deadline: break
        if replay and step > 1 and step in replay:
            ds = ds_type('train', a.size, dirs); ds.stems = replay[step]
            dl = torch.utils.data.DataLoader(ds, a.batch, shuffle=True, num_workers=0, drop_last=True); it = iter(dl)
            data_schedule.write(json.dumps({'step': step, 'stems': ds.stems}) + '\n')
        try: batch = next(it)
        except StopIteration:
            refreshed = ds_type('train', a.size, dirs) if not replay else ds
            if len(refreshed) > len(ds):
                ds = refreshed; dl = torch.utils.data.DataLoader(ds, a.batch, shuffle=True, num_workers=0, drop_last=True)
                print('DATASET_GROWN', len(ds), flush=True)
                data_schedule.write(json.dumps({'step': step, 'stems': ds.stems}) + '\n')
            it = iter(dl); batch = next(it)
        batch = batch.to(dev); x = batch[:, 0]; ei = (step - 1) % 3; style = STYLES[ei]; target = batch[:, ei + 1]
        semantic_mask = batch[:, 4, :1] if batch.shape[1] > 4 else None
        joint = step > a.steps - a.joint_last
        for n, p in model.named_parameters(): p.requires_grad_(n.startswith('experts.') or joint)
        model.train(); opt.zero_grad(set_to_none=True)
        for g in opt.param_groups: g['lr'] = a.lr * (.3 + .7 * (1 - step / a.steps))
        with torch.autocast('cuda', enabled=dev == 'cuda'):
            if joint: features = model.encode(x)
            else:
                with torch.no_grad(): features = model.encode(x)
            raw = model.experts[ei](*features)
            y = raw.clamp(0, 1) * .98 + raw * .02
            adversarial = y.new_zeros(()); critic_loss = y.new_zeros(())
            if critics is not None:
                disc = critics[ei]
                for p in disc.parameters(): p.requires_grad_(True)
                disc.train(); critic_opts[ei].zero_grad(set_to_none=True)
                artwork = torch.stack([reference_crop(style, a.size) for _ in range(a.batch)]).to(dev)
                with torch.autocast('cuda', enabled=False):
                    real_score = disc(torch.cat([target.detach(), artwork], 0).float())
                    fake_inputs = torch.cat([y.detach().clamp(0, 1), x], 0) if a.critic_texture else y.detach().clamp(0, 1)
                    fake_score = disc(fake_inputs.float())
                    critic_loss = F.relu(1 - real_score).mean() + F.relu(1 + fake_score).mean()
                if not torch.isfinite(critic_loss): raise FloatingPointError(f'Nonfinite critic at{step}')
                critic_loss.backward(); torch.nn.utils.clip_grad_norm_(disc.parameters(), 5.); critic_opts[ei].step()
                for p in disc.parameters(): p.requires_grad_(False)
                disc.eval()
                with torch.autocast('cuda', enabled=False): adversarial = -disc(y.float()).mean()
            fs = vgg(y)
            with torch.no_grad():
                fc = vgg(x)
                ft = vgg(target) if 'guide_perceptual' in cfg['weights'] else None
            content = sum(F.l1_loss(standardized(fs[j].float()), standardized(fc[j].float())) for j in (2, 3))
            patch, moment = bank.losses(fs, style)
            pixel = F.l1_loss(y, target)
            coarse = F.l1_loss(F.avg_pool2d(y, 16), F.avg_pool2d(target, 16))
            orientation = F.l1_loss(oriented_energy(y), oriented_energy(target)) if ei != 1 else y.new_zeros(())
            loss = content * cfg['weights']['content'][ei] + patch * cfg['weights']['patch'][ei] * a.patch_scale
            loss = loss + moment * cfg['weights']['moment'][ei] * a.patch_scale + pixel * cfg['weights']['pixel'][ei] + coarse * cfg['weights']['coarse']
            guide_perceptual = sum(F.l1_loss(fs[j].float(), ft[j].float()) for j in (1, 2, 3)) if ft is not None else y.new_zeros(())
            loss = loss + guide_perceptual * cfg['weights'].get('guide_perceptual', [0, 0, 0])[ei]
            semantic = y.new_zeros(()); head_edge = y.new_zeros(())
            if semantic_mask is not None:
                for j in (2, 3):
                    sm = F.interpolate(semantic_mask, size=fs[j].shape[-2:], mode='area')
                    df = (standardized(fs[j].float()) - standardized(fc[j].float())).abs()
                    semantic = semantic + (df * sm).sum() / (sm.sum() * fs[j].shape[1] + 1e-5)
                loss = loss + semantic * .20
                if a.head_edge_weight:
                    # Preserve fine semantic structure inside training-only COCO head masks,
                    # while leaving the student's ink/palette and all background brush fields free.
                    lum = y.new_tensor([.299, .587, .114]).view(1, 3, 1, 1)
                    yg, xg = (y.float()*lum).sum(1,keepdim=True), (x.float()*lum).sum(1,keepdim=True)
                    for dim in (-1,-2):
                        yd, xd = yg.diff(dim=dim), xg.diff(dim=dim)
                        mask = semantic_mask[..., :-1] if dim == -1 else semantic_mask[..., :-1, :]
                        scale = xd.square().mean((2,3),keepdim=True).sqrt().clamp_min(.03)
                        head_edge = head_edge + (((yd-xd)/scale).abs()*mask).sum()/(mask.sum()+1e-5)
                    loss = loss + a.head_edge_weight * head_edge
            loss = loss + orientation * cfg['weights']['orientation'][ei]
            direction = brush_direction_loss(y, target, x) if ei != 1 else y.new_zeros(())
            loss = loss + direction * cfg['weights']['brush_direction'][ei]
            loss = loss + adversarial * a.adversarial_weight * min(1., step / 500)
            equivariance = y.new_zeros(())
            if step % 2 == 0:
                dy, dx = random.choice(((1, 1), (-1, 3), (3, -1)))
                shifted = torch.roll(x, (dy, dx), (-2, -1))
                if joint: sf = model.encode(shifted)
                else:
                    with torch.no_grad(): sf = model.encode(shifted)
                sy = model.experts[ei](*sf).float()
                expected = torch.roll(y.detach(), (dy, dx), (-2, -1))
                equivariance = F.l1_loss(sy[..., 16:-16, 16:-16], expected[..., 16:-16, 16:-16])
                loss = loss + equivariance * cfg['weights']['equivariance'][ei]
            temporal = y.new_zeros(())
            if step % 4 == 0:
                temporal = temporal_loss(model, video, dev, 1, (ei,)); loss = loss + temporal * (4. if critics is not None else .7)
        if not torch.isfinite(loss): raise FloatingPointError(f'Nonfinite loss at{step}')
        scaler.scale(loss).backward(); scaler.unscale_(opt)
        norm = torch.nn.utils.clip_grad_norm_(model.parameters(), 2.)
        scaler.step(opt); scaler.update()
        last_step = step
        if step % 20 == 0:
            row = {'step': step, 'style': style, 'joint': joint, 'loss': float(loss), 'content': float(content), 'art_patch': float(patch),
                   'art_moment': float(moment), 'pixel': float(pixel), 'coarse': float(coarse), 'orientation': float(orientation),
                   'temporal': float(temporal), 'adversarial': float(adversarial), 'critic_loss': float(critic_loss), 'guide_perceptual': float(guide_perceptual), 'semantic_head': float(semantic), 'head_edge': float(head_edge), 'dataset_size': len(ds), 'brush_direction': float(direction), 'equivariance': float(equivariance), 'gradient_norm': float(norm), 'amp_scale': scaler.get_scale(), 'elapsed': time.time() - start}
            log.write(json.dumps(row) + '\n'); print(json.dumps(row), flush=True)
        if step % 100 == 0 or step == a.steps:
            torch.save({'model': model.state_dict(), 'opt': opt.state_dict(), 'step': step, 'config': cfg, 'critics': critics.state_dict() if critics is not None else None, 'critic_opts': [d.state_dict() for d in critic_opts],
                        'scaler': scaler.state_dict(), 'torch_rng': torch.get_rng_state(), 'cuda_rng': torch.cuda.get_rng_state_all() if dev == 'cuda' else None,
                        'python_rng': random.getstate(), 'numpy_rng': np.random.get_state()}, out / 'latest.pt')
        if step % a.eval_every == 0 or step == a.steps:
            ck = out / f'step_{step:06d}.pt'; torch.save({'model': model.state_dict(), 'step': step, 'config': cfg, 'critics': critics.state_dict() if critics is not None else None}, ck)
            dest = ROOT / 'reports/continuation' / a.run / f'{step:06d}'; dest.mkdir(parents=True, exist_ok=True)
            gallery(model, dest, dev)
            print('GALLERY', step, str(dest.relative_to(ROOT)), flush=True)
            (ROOT / 'supervisor/codex_status.json').write_text(json.dumps({'time': time.strftime('%Y-%m-%dT%H:%M:%S+08:00'),
                'implementation_owner': 'Codex authorized fallback', 'run': a.run, 'pid': __import__('os').getpid(), 'step': step,
                'checkpoint': str(ck.relative_to(ROOT)), 'gallery': str(dest.relative_to(ROOT)), 'art_acceptance': 'Needs real visual review; loss is not acceptance'}, indent=2))
    if last_step:
        torch.save({'model': model.state_dict(), 'opt': opt.state_dict(), 'step': last_step, 'config': cfg, 'critics': critics.state_dict() if critics is not None else None, 'critic_opts': [d.state_dict() for d in critic_opts],
                    'scaler': scaler.state_dict(), 'torch_rng': torch.get_rng_state(), 'cuda_rng': torch.cuda.get_rng_state_all() if dev == 'cuda' else None,
                    'python_rng': random.getstate(), 'numpy_rng': np.random.get_state()}, out / 'latest.pt')
    (out / 'finished.json').write_text(json.dumps({'step': last_step, 'elapsed': time.time() - start, 'stopped_by_deadline': time.time() >= deadline}))


if __name__ == '__main__': main()
