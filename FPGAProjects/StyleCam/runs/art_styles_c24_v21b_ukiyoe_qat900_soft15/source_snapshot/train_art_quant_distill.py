"""Distill a fixed-graph art checkpoint through the deployed integer arithmetic."""
import argparse
import hashlib
import json
import math
import random
import shutil
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

import golden
import hardware_qat
from art_region_v10 import van_gogh_loss, ukiyo_e_loss, ink_loss, source_regions, region_mean
from art_spatial_priors import luma
from tinystyle import QCfg, TinyStyleNet, macs_per_pixel
from train import ROOT, CropSet, image_list, camera_domain_augment


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--init', required=True)
    p.add_argument('--contract', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--steps', type=int, default=450)
    p.add_argument('--batch', type=int, default=2)
    p.add_argument('--crop', type=int, default=256)
    p.add_argument('--lr', type=float, default=2e-5)
    p.add_argument('--seed', type=int, default=20261004)
    p.add_argument('--save-every', type=int, default=150)
    p.add_argument('--soft-weight', type=float, default=1.0)
    p.add_argument('--style-weight', type=float, default=0.0)
    p.add_argument('--gradient-weight', type=float, default=0.0)
    p.add_argument('--ukiyo-hard-flat-weight', type=float, default=0.0)
    p.add_argument('--ink-balance-weight', type=float, default=0.0)
    p.add_argument('--ink-reference')
    a = p.parse_args()
    root = Path(ROOT)
    out = root / a.out
    out.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(4)
    random.seed(a.seed)
    np.random.seed(a.seed)
    torch.manual_seed(a.seed)
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA is required for this training run')
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    ck = torch.load(root / a.init, map_location='cpu', weights_only=False)
    contract = golden.load(str(root / a.contract))
    if ck['cfg'] != contract['cfg'] or ck['styles'] != contract['styles']:
        raise ValueError('Checkpoint and integer contract differ')
    student = TinyStyleNet(**ck['cfg']).cuda().train()
    student.load_state_dict(ck['sd'])
    teacher = TinyStyleNet(**ck['cfg']).cuda().eval()
    teacher.load_state_dict(ck['sd'])
    teacher.requires_grad_(False)
    ink_reference = None
    if a.ink_balance_weight:
        if not a.ink_reference:
            raise ValueError('--ink-reference is required with --ink-balance-weight')
        ref_ck = torch.load(root / a.ink_reference, map_location='cpu', weights_only=False)
        if ref_ck['cfg'] != ck['cfg'] or ref_ck['styles'] != ck['styles']:
            raise ValueError('Ink reference graph or styles differ')
        ink_reference = TinyStyleNet(**ck['cfg']).cuda().eval()
        ink_reference.load_state_dict(ref_ck['sd'])
        ink_reference.requires_grad_(False)
    for layer, item in zip(student.layers, contract['layers']):
        if not np.isclose(float(layer.aq.scale()), item['s_y'], rtol=1e-6, atol=1e-10):
            raise ValueError(f"Activation scale mismatch: {layer.spec['name']}")
    train, held = image_list()
    if set(train) & set(held):
        raise ValueError('Training and development images overlap')
    loader = torch.utils.data.DataLoader(CropSet(train, a.crop), batch_size=a.batch,
                                         shuffle=True, drop_last=True, num_workers=0)
    config = dict(args=vars(a), init_sha256=sha(root / a.init),
                  contract_json_sha256=sha(str(root / a.contract) + '.json'),
                  contract_npz_sha256=sha(str(root / a.contract) + '.npz'),
                  cfg=ck['cfg'], styles=ck['styles'],
                  params=sum(p.numel() for p in student.parameters()),
                  conv_MACs_VGA=macs_per_pixel(student.specs)[0] * 640 * 480,
                  graph_changed=False, board_validated=False,
                  ink_reference_sha256=sha(root / a.ink_reference) if ink_reference else None,
                  train_files=[Path(f).name for f in train],
                  development_files=[Path(f).name for f in held])
    (out / 'config.json').write_text(json.dumps(config, indent=2), encoding='utf-8')
    snap = out / 'source_snapshot'
    snap.mkdir()
    for name in ('train_art_quant_distill.py', 'hardware_qat.py', 'tinystyle.py',
                 'golden.py', 'art_region_v10.py', 'art_spatial_priors.py',
                 'art_material_v7.py', 'art_structure_v8.py'):
        shutil.copy2(root / 'algo' / name, snap / name)
    opt = torch.optim.Adam(student.parameters(), lr=a.lr)
    QCfg.observe = False
    start = time.monotonic()
    step = 0
    window = []
    def save(name):
        path = out / (name + '.tmp')
        torch.save(dict(cfg=student.cfg, styles=ck['styles'],
                        sd={k: v.detach().cpu() for k, v in student.state_dict().items()},
                        qat=True, it=step, args=vars(a),
                        needs_new_export=True, board_validated=False), path)
        path.replace(out / name)
    with (out / 'train.jsonl').open('w', encoding='utf-8') as log:
        while step < a.steps:
            for xb in loader:
                si = step % len(ck['styles'])
                x = xb.cuda().float() / 255
                xa = camera_domain_augment(x * 255, .3) / 255
                style = torch.full((len(x),), si, device='cuda', dtype=torch.long)
                QCfg.enabled = False
                with torch.no_grad():
                    target = teacher(xa, style)
                QCfg.enabled = True
                hard = hardware_qat.forward(student, xa, style, contract)
                QCfg.enabled = False
                soft = student(xa, style)
                hard_l1 = F.l1_loss(hard, target)
                soft_l1 = F.l1_loss(soft, target)
                hard_mse = F.mse_loss(hard, target)
                def gradient_l1(a, b):
                    ay, by = luma(a), luma(b)
                    return (F.l1_loss(ay[:, :, 1:] - ay[:, :, :-1],
                                      by[:, :, 1:] - by[:, :, :-1]) +
                            F.l1_loss(ay[:, :, :, 1:] - ay[:, :, :, :-1],
                                      by[:, :, :, 1:] - by[:, :, :, :-1]))
                grad = gradient_l1(hard, target) + gradient_l1(soft, target)
                style_loss = hard.new_zeros(())
                if a.style_weight:
                    def regional(y):
                        if si == 0:
                            z = van_gogh_loss(y, xa)
                            return 7 * z['stroke'] + 3 * z['continuity'] + 5 * z['edges']
                        if si == 1:
                            z = ukiyo_e_loss(y, xa)
                            return 4 * z['flat'] + 1.5 * z['palette'] + 8 * z['outline'] + 2 * z['dark_line']
                        z = ink_loss(y, xa)
                        return 2.5 * z['dense'] + 3 * z['paper'] + 5 * z['strong_edge'] + 1.5 * z['fade']
                    style_loss = regional(hard) + regional(soft)
                hard_flat = hard.new_zeros(())
                if si == 1 and a.ukiyo_hard_flat_weight:
                    interior = source_regions(xa)[4]
                    horizontal = (hard[:, :, :, 1:] - hard[:, :, :, :-1]).abs()
                    vertical = (hard[:, :, 1:, :] - hard[:, :, :-1, :]).abs()
                    hard_flat = (region_mean(F.relu(horizontal - .006),
                                             torch.minimum(interior[:, :, :, 1:], interior[:, :, :, :-1])) +
                                 region_mean(F.relu(vertical - .006),
                                             torch.minimum(interior[:, :, 1:, :], interior[:, :, :-1, :])))
                ink_balance = hard.new_zeros(())
                if si == 2 and ink_reference is not None:
                    with torch.no_grad():
                        reference = luma(ink_reference(xa, style))
                        _, _, _, _, _, subject, paper, _ = source_regions(xa)
                    ink_balance = sum(region_mean((luma(y) - reference).abs(), mask)
                                      for y in (hard, soft) for mask in (subject, paper))
                loss = (5 * hard_l1 + a.soft_weight * soft_l1 + 2 * hard_mse +
                        a.gradient_weight * grad + a.style_weight * style_loss +
                        a.ukiyo_hard_flat_weight * hard_flat +
                        a.ink_balance_weight * ink_balance)
                lr = a.lr * (.3 + .7 * .5 * (1 + math.cos(math.pi * step / a.steps)))
                for group in opt.param_groups:
                    group['lr'] = lr
                opt.zero_grad(set_to_none=True)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(student.parameters(), 2, error_if_nonfinite=True)
                opt.step()
                step += 1
                window.append((float(hard_l1), float(soft_l1), float(hard_mse),
                               float(grad), float(style_loss), float(hard_flat), float(ink_balance)))
                if step % 50 == 0 or step == a.steps:
                    row = dict(step=step, seconds=time.monotonic() - start,
                               hard_l1=float(np.mean([v[0] for v in window])),
                               soft_l1=float(np.mean([v[1] for v in window])),
                               hard_mse=float(np.mean([v[2] for v in window])))
                    row['gradient_l1'] = float(np.mean([v[3] for v in window]))
                    row['style_loss'] = float(np.mean([v[4] for v in window]))
                    row['ukiyo_hard_flat'] = float(np.mean([v[5] for v in window]))
                    row['ink_balance'] = float(np.mean([v[6] for v in window]))
                    log.write(json.dumps(row) + '\n')
                    log.flush()
                    print(json.dumps(row), flush=True)
                    window = []
                if step % a.save_every == 0 or step == a.steps:
                    save(f'step_{step:05}.pt')
                if step >= a.steps:
                    break
    QCfg.enabled = False
    save('student.pt')
    print('SAVED', out, flush=True)


if __name__ == '__main__':
    main()
