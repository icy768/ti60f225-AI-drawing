"""QAT fine-tune (optional) -> convert -> single all-style INT8 pack + TorchScript + checks.

Pack 'TRIV3\\0\\0\\0' layout (little endian):
  header <8s I I I I>: magic, len(meta_zlib), len(payload), n_conv, version=3
  meta  : zlib(JSON) with graph, per-conv shapes/qparams/offsets, add/cat/input qparams
  payload per conv: int8 weights, int32 bias (in acc units), int32 Q31 multiplier, int8 exponent
Everything the integer engine needs for all three styles is inside; FP32 weight scales are not needed.
"""
import sys, json, time, copy, struct, zlib, hashlib, argparse, pathlib, warnings, random
import numpy as np, torch
from torch import nn
from torch.nn import functional as F
HERE = pathlib.Path(__file__).resolve().parent; ROOT = HERE.parent
sys.path.insert(0, str(HERE)); sys.path.insert(1, str(ROOT))
from model import TriStyleV3, STYLES, fuse_list, model_for_state
from graph import build_graph
from torch.ao.quantization import fuse_modules_qat, get_default_qat_qconfig, prepare_qat, convert
from torch.ao.quantization import disable_observer, enable_observer
warnings.filterwarnings('ignore', message='.*must run observer.*')
LIMIT = 500000
QAT_DIRS = ['vangogh', 'ukiyoe', 'ink']  # set from --targets

def prepared(fp):
    q = copy.deepcopy(fp).cpu().train(); fuse_modules_qat(q, fuse_list(q), inplace=True)
    q.qconfig = get_default_qat_qconfig('onednn'); prepare_qat(q, inplace=True); return q

def qat_to_plain(q):
    """QAT-trained fused model -> plain float TriStyleV3 with identical weights (no BN, so fused conv == conv)."""
    src = q.state_dict(); plain = model_for_state(src).eval(); ref = plain.state_dict()
    new = {k: src[k].detach().clone().float() for k in ref}  # every plain key exists in the QAT state (same names)
    plain.load_state_dict(new, strict=True); return plain

def to_int(q):
    q = copy.deepcopy(q).cpu().eval(); return convert(q, inplace=False).eval()

def qat(fp, steps, run_dir, dev='cuda', lr=5e-5):
    from train import Paired, VGG, style_loss, WEIGHTS, Video, temporal_loss
    torch.backends.quantized.engine = 'onednn'
    q = prepared(fp).to(dev); vgg = VGG().to(dev); vid = Video()
    ds = Paired('train', 256, QAT_DIRS); dl = torch.utils.data.DataLoader(ds, 4, shuffle=True, num_workers=0, drop_last=True)
    opt = torch.optim.Adam(q.parameters(), lr); it = iter(dl); log = (run_dir / 'qat_metrics.jsonl').open('a', buffering=1)
    for step in range(1, steps + 1):
        try: b = next(it)
        except StopIteration: it = iter(dl); b = next(it)
        b = b.to(dev); x = b[:, 0]; loss = 0.
        if step == int(steps * .7): q.apply(disable_observer)  # freeze ranges for the final 30%
        for i in range(3):
            y = q(x, i).clamp(0, 1); fy = vgg(y)
            with torch.no_grad(): ft = vgg(b[:, 1 + i])
            l, _ = style_loss(y, b[:, 1 + i], fy, ft, WEIGHTS[STYLES[i]]); loss = loss + l
        opt.zero_grad(); loss.backward(); nn.utils.clip_grad_norm_(q.parameters(), 1.); opt.step()
        if step % 50 == 0: log.write(json.dumps({'step': step, 'loss': float(loss)}) + '\n'); print('QAT', step, float(loss), flush=True)
    q.apply(disable_observer); return q.cpu()

def calibrate(fp, n=32, robust=False):
    q = prepared(fp); q.apply(torch.ao.quantization.disable_fake_quant)
    bounds, hooks = {}, []
    if robust:
        # Calibrate from legal TRAINING images only. Rare padding/outlier spikes
        # otherwise waste almost all activation codes in the ink decoder.
        for name, module in q.named_modules():
            if isinstance(module, torch.ao.quantization.FakeQuantizeBase) and 'weight_fake_quant' not in name:
                def hook(mod, args, key=name):
                    v=args[0].detach().float().flatten(); stride=max(1,v.numel()//32768)
                    vals=torch.quantile(v[::stride],v.new_tensor([.001,.999]))
                    lo,hi=float(vals[0]),float(vals[1])
                    if key in bounds: lo=min(lo,bounds[key][0]);hi=max(hi,bounds[key][1])
                    bounds[key]=(lo,hi)
                hooks.append(module.register_forward_pre_hook(hook))
    paths = json.loads((ROOT / 'data/splits.json').read_text())['train'][:n]
    from PIL import Image
    with torch.no_grad():
        for p in paths:
            im = Image.open(ROOT / p).convert('RGB').resize((320, 240))
            x = torch.from_numpy(np.array(im)).permute(2, 0, 1)[None].float() / 255
            for s in range(3): q(x, s)
    for hook in hooks: hook.remove()
    if robust:
        for name,module in q.named_modules():
            if name in bounds:
                lo,hi=bounds[name]; obs=module.activation_post_process
                obs.min_val.copy_(torch.tensor(min(lo,0.),device=obs.min_val.device))
                obs.max_val.copy_(torch.tensor(max(hi,1e-6),device=obs.max_val.device))
                scale,zp=module.calculate_qparams();module.scale.resize_(scale.shape).copy_(scale);module.zero_point.resize_(zp.shape).copy_(zp)
        q._robust_calibration_bounds=bounds
    q.apply(torch.ao.quantization.enable_fake_quant); q.apply(disable_observer); return q

def frexp_q31(r):
    f, e = np.frexp(np.asarray(r, np.float64)); m = np.rint(f * 2 ** 31).astype(np.int64)
    o = m == 2 ** 31; m[o] //= 2; e = e.astype(np.int64); e[o] += 1; return m, e

def pack(qi, fp, path):
    """qi: converted int model. Gather qparams by running a hook pass."""
    ins = {}; hs = []
    for n, m in qi.named_modules():
        if isinstance(m, torch.ao.nn.quantized.Conv2d):
            hs.append(m.register_forward_hook(lambda mod, a, o, k=n: ins.__setitem__(k, (float(a[0].q_scale()), int(a[0].q_zero_point())))))
    with torch.no_grad():
        for s in range(3): qi(torch.rand(1, 3, 32, 32), s)
    for h in hs: h.remove()
    payload = bytearray(); convs = []; tot = {'weight_int8': 0, 'bias_int32': 0, 'multiplier_int32': 0, 'exponent_int8': 0}
    def put(a, k):
        o = len(payload); payload.extend(a.tobytes()); tot[k] += a.nbytes; return [o, a.nbytes]
    for n, m in qi.named_modules():
        if not isinstance(m, torch.ao.nn.quantized.Conv2d): continue
        key = n[:-5] if n.endswith('.conv') else n
        w = m.weight(); assert (w.q_per_channel_zero_points() == 0).all()
        ws = w.q_per_channel_scales().double().numpy(); si, zi = ins[n]; so, zo = float(m.scale), int(m.zero_point)
        bias = m.bias().detach().double().numpy(); bi = np.rint(bias / (si * ws)).astype(np.int64)
        assert np.abs(bi).max() < 2 ** 31
        # host TorchScript uses exactly the rounded INT32 bias stored in the pack (same contract)
        m.set_weight_bias(w, torch.from_numpy((bi * si * ws).astype(np.float32)))
        mult, exp = frexp_q31(si * ws / so); assert np.abs(exp).max() < 127
        relu = isinstance(m, torch.ao.nn.intrinsic.quantized.ConvReLU2d)
        acc_bound = np.abs(bi) + max(zi, 255 - zi) * np.abs(w.int_repr().numpy().astype(np.int64)).reshape(w.shape[0], -1).sum(1)
        assert acc_bound.max() < 2 ** 31, 'INT32 accumulator bound exceeded'
        convs.append({'name': key + '.conv', 'shape': list(w.shape), 'stride': list(m.stride), 'padding': list(m.padding), 'groups': m.groups,
                      'relu': relu, 'in_zp': zi, 'out_zp': zo, 'in_scale': si, 'out_scale': so, 'accumulator_absolute_bound': int(acc_bound.max()),
                      'weight': put(w.int_repr().numpy().astype('i1'), 'weight_int8'), 'bias': put(bi.astype('<i4'), 'bias_int32'),
                      'multiplier': put(mult.astype('<i4'), 'multiplier_int32'), 'exponent': put(exp.astype('i1'), 'exponent_int8')})
    qparams = {}
    for n, m in qi.named_modules():
        if isinstance(m, torch.ao.nn.quantized.QFunctional): qparams[n] = [float(m.scale), int(m.zero_point)]
        if isinstance(m, torch.ao.nn.quantized.Quantize): qparams[n] = [float(m.scale), int(m.zero_point)]
    meta = {'format': 'TRISTYLE_V3_INT8', 'styles': list(STYLES), 'convs': convs, 'qparams': qparams, 'graph': build_graph(fp),
            'arith': 'acc=sum((x-in_zp)*w)+bias (INT32); y=sat_u8(round_half_even(acc*mult*2^(exp-31))+out_zp); relu: y>=out_zp',
            'add_cat': 'requant each input to output scale with Q31 multiplier and 16 guard bits, sum, round once'}
    from int_contract import attach_integer_constants
    attach_integer_constants(meta)
    mz = zlib.compress(json.dumps(meta, separators=(',', ':')).encode(), 9)
    hdr = struct.pack('<8sIIII', b'TRIV3\0\0\0', len(mz), len(payload), len(convs), 3)
    blob = hdr + mz + bytes(payload); path.write_bytes(blob)
    tot.update({'header': len(hdr), 'metadata_zlib': len(mz), 'payload': len(payload), 'total_bytes': len(blob), 'limit': LIMIT, 'fits': len(blob) <= LIMIT,
                'sha256': hashlib.sha256(blob).hexdigest(), 'n_conv': len(convs), 'per_part': {}, 'max_conservative_INT32_accumulator_bound': max(c['accumulator_absolute_bound'] for c in convs)})
    for c in convs:
        part = 'shared' if not c['name'].startswith('experts.') else STYLES[int(c['name'].split('.')[1])]
        tot['per_part'][part] = tot['per_part'].get(part, 0) + sum(c[k][1] for k in ('weight', 'bias', 'multiplier', 'exponent'))
    return tot

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--checkpoint', required=True); ap.add_argument('--out', required=True)
    ap.add_argument('--qat-steps', type=int, default=0); ap.add_argument('--targets', default='vangogh5,ukiyoe3,ink5'); ap.add_argument('--device', default='cuda'); ap.add_argument('--weights', default='')
    ap.add_argument('--qat-objective', choices=('targets', 'preserve'), default='targets', help='preserve: quantize selected art checkpoint without regressing to procedural targets')
    ap.add_argument('--qat-batch', type=int, default=2)
    ap.add_argument('--robust-calibration', action='store_true', help='Training-only .1/99.9 percentiles, freeze activation ranges through QAT')
    a = ap.parse_args()
    global QAT_DIRS; QAT_DIRS = a.targets.split(',')
    if a.weights:
        from train import WEIGHTS
        for k, v in json.loads(a.weights).items(): WEIGHTS[k].update(v)
    torch.set_num_threads(4); torch.backends.quantized.engine = 'onednn'; random.seed(1); torch.manual_seed(1)
    out = ROOT / a.out; out.mkdir(parents=True, exist_ok=True)
    (out / 'export_config.json').write_text(json.dumps({**vars(a), 'seed': 1, 'torch': torch.__version__, 'quantized_engine': 'onednn',
        'source_checkpoint_sha256': hashlib.sha256((ROOT / a.checkpoint).read_bytes()).hexdigest(),
        'export_source_sha256': hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()}, indent=2))
    sd = torch.load(ROOT / a.checkpoint, map_location='cpu', weights_only=False); fp = model_for_state(sd['model']).eval(); fp.load_state_dict(sd['model'])
    q = calibrate(fp, robust=a.robust_calibration)
    if a.robust_calibration: (out/'robust_calibration_bounds.json').write_text(json.dumps(q._robust_calibration_bounds,indent=1))
    if a.qat_steps: q = _qat_from(q, fp, a.qat_steps, out, dev=a.device, objective=a.qat_objective, batch_size=a.qat_batch, freeze_activation=a.robust_calibration)
    q.eval(); torch.save(q.state_dict(), out / 'fake_int8_state.pt')
    if a.qat_steps:
        # same-checkpoint FLOAT reference: QAT-trained weights with fake-quant disabled
        pre_qat = fp; fp = qat_to_plain(q)
        chk = copy.deepcopy(q); chk.apply(torch.ao.quantization.disable_fake_quant); chk.eval()
        with torch.no_grad():
            xx = torch.rand(1, 3, 64, 80); dmax = max(float((fp(xx, s) - chk(xx, s)).abs().max()) for s in range(3))
        assert dmax < 1e-4, f'plain QAT float != fake-disabled QAT ({dmax})'
        torch.save({'model': pre_qat.state_dict(), 'kind': 'pre-QAT FP32 art baseline (source checkpoint weights)', 'source_checkpoint': a.checkpoint}, out / 'pre_qat_fp32.pt')
    qi = to_int(q); tot = pack(qi, fp, out / 'tristyle_v3_all.bin')  # graph from unfused topology
    (out / 'pack_bytes.json').write_text(json.dumps(tot, indent=1)); print(json.dumps(tot, indent=1), flush=True)
    ts = torch.jit.script(qi); ts.save(str(out / 'tristyle_v3_int8.ts'))
    torch.save({'model': fp.state_dict(), 'kind': ('QAT-trained weights as plain float TriStyleV3 (same checkpoint as INT8 pack)' if a.qat_steps else 'source FP32 weights (PTQ; same weights as INT8 pack)'),
                'source_checkpoint': a.checkpoint, 'step': sd.get('step'), 'qat_steps': a.qat_steps, 'qat_objective': a.qat_objective}, out / 'tristyle_v3_fp32.pt')
    # fresh reload test of the delivered float file
    chk = model_for_state(fp.state_dict()).eval(); chk.load_state_dict(torch.load(out / 'tristyle_v3_fp32.pt', map_location='cpu', weights_only=False)['model'], strict=True)
    with torch.no_grad():
        xx = torch.rand(1, 3, 64, 80); assert max(float((chk(xx, s) - fp(xx, s)).abs().max()) for s in range(3)) == 0.0
    if not tot['fits']: raise RuntimeError('pack exceeds 500000 bytes')
    # FP32 vs fake vs integer on all 17 test scenes at 320x240 (quantisation retention only)
    from PIL import Image
    from skimage.metrics import structural_similarity
    from train import save_grid
    rows = []; grid = []; (out / 'comparison').mkdir(exist_ok=True)
    for f in sorted((ROOT / 'data/test').glob('*.png')):
        im = Image.open(f).convert('RGB').resize((320, 240), Image.Resampling.LANCZOS); x = torch.from_numpy(np.array(im)).permute(2, 0, 1)[None].float() / 255
        g = [np.array(im)]
        for s in range(3):
            with torch.no_grad():
                yf = fp(x, s).clamp(0, 1); yq = q(x, s).clamp(0, 1); t = time.perf_counter(); yi = ts(x, s).clamp(0, 1); dt = time.perf_counter() - t
            A = lambda y: (y[0].permute(1, 2, 0).numpy() * 255).round().astype(np.uint8)
            fa, ia = A(yf), A(yi); Image.fromarray(ia).save(out / 'comparison' / f'{f.stem}_{STYLES[s]}_int8.png'); Image.fromarray(fa).save(out / 'comparison' / f'{f.stem}_{STYLES[s]}_fp32.png')
            Image.fromarray(A(yq)).save(out / 'comparison' / f'{f.stem}_{STYLES[s]}_fake_int8.png')
            mse = float(((fa.astype(float) - ia) / 255) ** 2 .mean()) if False else float((((fa.astype(float) - ia) / 255) ** 2).mean())
            rows.append({'scene': f.stem, 'style': STYLES[s], 'fp32_vs_int8_PSNR': -10 * np.log10(max(mse, 1e-12)),
                         'fp32_vs_int8_SSIM': float(structural_similarity(fa, ia, channel_axis=2)), 'fake_vs_int8_maxabs_LSB': float((yq - yi).abs().max() * 255),
                         'cpu_int8_sec_320x240': dt})
            g.append(ia)
        grid.append((f.stem + ' INT8', g))
    save_grid(grid, out / 'int8_comparison.jpg')
    summ = {s: {k: float(np.mean([r[k] for r in rows if r['style'] == s])) for k in ('fp32_vs_int8_PSNR', 'fp32_vs_int8_SSIM')} for s in STYLES}
    (out / 'quantization_metrics.json').write_text(json.dumps({'checkpoint': a.checkpoint, 'qat_steps': a.qat_steps, 'qat_objective': a.qat_objective, 'targets': QAT_DIRS, 'summary': summ, 'rows': rows,
        'float_reference': 'QAT weights with fake-quant disabled (same checkpoint)' if a.qat_steps else 'source FP32 checkpoint (PTQ, same weights)', 'note': 'Same-checkpoint quantisation retention only; not artistic quality or FPGA throughput.'}, indent=1))
    print(json.dumps(summ, indent=1))

def _qat_from(q, fp, steps, out, dev='cuda', lr=3e-5, objective='targets', batch_size=2, freeze_activation=False):
    """QAT starting from calibrated observers."""
    from train import Paired, VGG, style_loss, WEIGHTS
    q = q.to(dev).train(); q.apply(enable_observer); vgg = VGG().to(dev)
    if freeze_activation:
        for name,module in q.named_modules():
            if isinstance(module,torch.ao.quantization.FakeQuantizeBase) and 'weight_fake_quant' not in name: module.disable_observer()
    teacher = copy.deepcopy(fp).to(dev).eval() if objective == 'preserve' else None
    if teacher is not None:
        for p in teacher.parameters(): p.requires_grad_(False)
    ds = Paired('train', 256, QAT_DIRS); dl = torch.utils.data.DataLoader(ds, batch_size, shuffle=True, num_workers=0, drop_last=True)
    opt = torch.optim.Adam(q.parameters(), lr); it = iter(dl); log = (out / 'qat_metrics.jsonl').open('a', buffering=1)
    qat_start = time.time()
    for step in range(1, steps + 1):
        try: b = next(it)
        except StopIteration: it = iter(dl); b = next(it)
        b = b.to(dev); x = b[:, 0]; loss = 0.
        opt.zero_grad(set_to_none=True)
        if step == int(steps * .6): q.apply(disable_observer)
        for i in range(3):
            y = q(x, i); y = y.clamp(0, 1); fy = vgg(y)
            with torch.no_grad():
                target = teacher(x, i).clamp(0, 1) if teacher is not None else b[:, 1 + i]
                ft = vgg(target)
            l, _ = style_loss(y, target, fy, ft, WEIGHTS[STYLES[i]])
            l.backward(); loss += float(l.detach())  # accumulate all experts; release each feature graph promptly
        nn.utils.clip_grad_norm_(q.parameters(), 1.); opt.step()
        if step == 1 or step % 10 == 0 or step == steps:
            row = {'step': step, 'loss': loss, 'elapsed': time.time() - qat_start, 'objective': objective, 'device': dev, 'batch': batch_size}
            log.write(json.dumps(row) + '\n'); print('QAT', json.dumps(row), flush=True)
    q.apply(disable_observer); return q.cpu().eval()

if __name__ == '__main__':
    main()
