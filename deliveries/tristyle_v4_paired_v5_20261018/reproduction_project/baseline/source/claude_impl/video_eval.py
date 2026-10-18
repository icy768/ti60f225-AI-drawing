"""Held-out real video (Sintel trailer frames >= evaluation_start_frame) for FP32 or INT8 TorchScript.
Writes a 4-panel mp4, sample frames and visibility-masked flow-warp MAE (input-flow, Farneback).
Usage: video_eval.py --checkpoint X.pt | --ts X.ts  --out DIR [--frames N] [--size 320x240]
"""
import sys, json, time, argparse, pathlib, hashlib
import numpy as np, cv2, torch
HERE = pathlib.Path(__file__).resolve().parent; ROOT = HERE.parent; sys.path.insert(0, str(HERE))
from model import TriStyleV3, STYLES, model_for_state

def main():
    ap = argparse.ArgumentParser(); mode = ap.add_mutually_exclusive_group(required=True); mode.add_argument('--checkpoint'); mode.add_argument('--ts'); mode.add_argument('--pack'); ap.add_argument('--out', required=True)
    ap.add_argument('--frames', type=int, default=150); ap.add_argument('--size', default='320x240'); ap.add_argument('--start', type=int, default=None); ap.add_argument('--device', default='cuda'); a = ap.parse_args()
    W, H = map(int, a.size.split('x')); torch.set_num_threads(4); torch.backends.quantized.engine = 'onednn'
    if a.pack:
        from int_ref import IntGraph
        m = IntGraph(ROOT / a.pack); dev = 'cpu'; tag = 'integer_reference'
    elif a.ts: m = torch.jit.load(str(ROOT / a.ts)).eval(); dev = 'cpu'; tag = 'int8'
    else:
        dev = a.device; tag = 'fp32'; state = torch.load(ROOT / a.checkpoint, map_location='cpu', weights_only=False)['model']; m = model_for_state(state).to(dev).eval(); m.load_state_dict(state)
    meta = json.loads((ROOT / 'data/video/train_pairs/manifest.json').read_text())
    cap = cv2.VideoCapture(str(ROOT / meta['source'])); start = meta['evaluation_start_frame'] if a.start is None else a.start
    maxtrain = max(p['frame'] for p in meta['pairs']); assert start > maxtrain + 1, 'start overlaps training pairs'; cap.set(cv2.CAP_PROP_POS_FRAMES, start)
    out = ROOT / a.out; out.mkdir(parents=True, exist_ok=True)
    assert W % 8 == H % 8 == 0, 'video dimensions must be multiples of8'
    wr = cv2.VideoWriter(str(out / f'heldout_{tag}.mp4'), cv2.VideoWriter_fourcc(*'mp4v'), meta['fps'], (W * 4, H))
    assert wr.isOpened(), 'video encoder failed to open'
    prev = prevy = None; rows = []; gy, gx = np.mgrid[:H, :W].astype(np.float32)
    with torch.no_grad():
        for i in range(a.frames):
            ok, bgr = cap.read()
            if not ok: break
            bgr = cv2.resize(bgr, (W, H), interpolation=cv2.INTER_AREA); rgb = bgr[:, :, ::-1].copy()
            x = torch.from_numpy(rgb).permute(2, 0, 1)[None].float().to(dev) / 255; ys = []; r = {'frame': start + i}
            for s in range(3):
                t = time.perf_counter()
                if a.pack:
                    u = torch.from_numpy(rgb).permute(2, 0, 1)[None]
                    y = m(u, s).float() / 255
                else: y = m(x, s).clamp(0, 1)
                if dev == 'cuda': torch.cuda.synchronize()
                r[f'{STYLES[s]}_host_ms'] = 1000 * (time.perf_counter() - t); ys.append(y[0].permute(1, 2, 0).cpu().numpy())
            if prev is not None:
                ga = cv2.cvtColor(prev, cv2.COLOR_RGB2GRAY); gb = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
                cut = float(np.abs(ga.astype(float) - gb).mean()) > 30; r['scene_cut'] = cut
                if not cut:
                    fl = cv2.calcOpticalFlowFarneback(gb, ga, None, .5, 3, 15, 3, 5, 1.2, 0); mx, my = gx + fl[..., 0], gy + fl[..., 1]
                    wp = cv2.remap(prev.astype(np.float32) / 255, mx, my, cv2.INTER_LINEAR); diff = np.abs(wp - rgb / 255.).mean(2)
                    mask = (diff < .08) & (mx > 1) & (mx < W - 2) & (my > 1) & (my < H - 2); r['valid_frac'] = float(mask.mean())
                    r['input_warp_MAE'] = float(diff[mask].mean()) if mask.any() else None
                    for s in range(3):
                        wy = cv2.remap(prevy[s], mx, my, cv2.INTER_LINEAR)
                        if mask.any(): r[f'{STYLES[s]}_warp_MAE'] = float(np.abs(wy - ys[s]).mean(2)[mask].mean())
            rows.append(r)
            panels = [bgr] + [np.ascontiguousarray((v[:, :, ::-1] * 255).round().astype(np.uint8)) for v in ys]
            for p, l in zip(panels, ['input (held-out)'] + list(STYLES)):
                cv2.putText(p, l, (6, 16), cv2.FONT_HERSHEY_SIMPLEX, .45, (0, 0, 0), 3); cv2.putText(p, l, (6, 16), cv2.FONT_HERSHEY_SIMPLEX, .45, (255, 255, 255), 1)
            fr = np.concatenate(panels, 1); wr.write(fr)
            if i % 30 == 0: cv2.imwrite(str(out / f'{tag}_frame_{start + i:05d}.jpg'), fr)
            prev, prevy = rgb, ys
            if (i+1) % 10 == 0: print('VIDEO_FRAME', start+i, flush=True)
    wr.release()
    model_path = a.pack or a.ts or a.checkpoint
    summ = {'source': meta['source'], 'license': 'Sintel trailer, Blender Foundation, CC BY 3.0 (sources/Sintel_license.html)', 'heldout_start_frame': start, 'max_training_pair_first_frame': maxtrain, 'max_training_pair_second_frame': maxtrain+1, 'heldout_rule': f'action segment begins {start}, strictly beyond training pair second-frame {maxtrain+1}; no optimizer uses heldout frames',
            'frames': len(rows), 'size': [W, H], 'model': model_path, 'model_sha256': hashlib.sha256((ROOT/model_path).read_bytes()).hexdigest(), 'mode': tag,
            'input_warp_MAE_mean': float(np.mean([r['input_warp_MAE'] for r in rows if r.get('input_warp_MAE') is not None]))}
    for s in STYLES:
        e = [r[f'{s}_warp_MAE'] for r in rows if f'{s}_warp_MAE' in r]
        summ[s] = {'warp_MAE_mean': float(np.mean(e)) if e else None, 'pairs': len(e), 'host_ms_mean': float(np.mean([r[f'{s}_host_ms'] for r in rows]))}
    summ['note'] = 'Warp MAE on RGB [0,1] over visibility-masked pixels using input-frame Farneback flow; host timing is PC CPU/GPU, NOT FPGA throughput.'
    (out / f'video_{tag}_metrics.json').write_text(json.dumps({'summary': summ, 'rows': rows}, indent=1)); print(json.dumps(summ, indent=1))

if __name__ == '__main__':
    main()
