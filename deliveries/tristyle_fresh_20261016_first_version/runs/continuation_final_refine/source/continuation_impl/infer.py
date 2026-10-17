"""Image inference for this project's v3 FP32, oneDNN INT8 or pack-only integer graph."""
import argparse, hashlib, json, pathlib, sys, time
import numpy as np
import torch
from PIL import Image
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'claude_impl'))
from model import TriStyleV3, STYLES, model_for_state


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--model', required=True); ap.add_argument('--input', required=True); ap.add_argument('--output', required=True)
    ap.add_argument('--style', choices=(*STYLES, 'all'), default='all')
    ap.add_argument('--backend', choices=('fp32', 'int8', 'integer-reference'), default='fp32')
    ap.add_argument('--size', type=int, nargs=2, metavar=('WIDTH', 'HEIGHT'))
    ap.add_argument('--device', choices=('cpu', 'cuda'), default='cpu')
    a = ap.parse_args(); torch.set_num_threads(4)
    mp = pathlib.Path(a.model).resolve(); ip = pathlib.Path(a.input).resolve(); out = pathlib.Path(a.output).resolve()
    im = Image.open(ip).convert('RGB'); original = list(im.size)
    if a.size:
        assert min(a.size) >= 16, 'model input dimensions must be >=16'
        im = im.resize(a.size, Image.Resampling.LANCZOS)
    rgb = np.array(im, copy=True); h, w = rgb.shape[:2]
    assert min(h, w) >= 16, 'model input dimensions must be >=16'
    rgb = np.pad(rgb, ((0, (-h) % 8), (0, (-w) % 8), (0, 0)), mode='edge')
    x = torch.from_numpy(rgb.copy()).permute(2, 0, 1)[None]
    if a.backend == 'fp32':
        state = torch.load(mp, map_location='cpu', weights_only=False)['model']
        model = model_for_state(state).eval().to(a.device); model.load_state_dict(state, strict=True)
        inp = x.float().to(a.device) / 255
    else:
        if a.device != 'cpu': raise ValueError('INT8 backends execute on CPU; use --device cpu')
        if a.backend == 'int8':
            torch.backends.quantized.engine = 'onednn'
            model = torch.jit.load(str(mp), map_location='cpu').eval(); inp = x.float() / 255
        else:
            from int_ref import IntGraph
            model = IntGraph(mp); inp = x
    rows = []
    if a.style == 'all': out.mkdir(parents=True, exist_ok=True)
    else: out.parent.mkdir(parents=True, exist_ok=True)
    with torch.inference_mode():
        for i, style in enumerate(STYLES):
            if a.style not in ('all', style): continue
            t = time.perf_counter(); y = model(inp, i)
            if a.device == 'cuda': torch.cuda.synchronize()
            elapsed = time.perf_counter() - t
            if a.backend != 'integer-reference': y = (y.clamp(0, 1) * 255).round().to(torch.uint8)
            arr = y[0, :, :h, :w].permute(1, 2, 0).cpu().numpy()
            op = out / f'{ip.stem}_{style}.png' if a.style == 'all' else out
            Image.fromarray(arr).save(op); rows.append({'style': style, 'output': str(op), 'host_sec': elapsed})
    print(json.dumps({'model': str(mp), 'sha256': hashlib.sha256(mp.read_bytes()).hexdigest(), 'backend': a.backend,
                      'original_size': original, 'model_size_before_edge_padding': [w, h], 'results': rows,
                      'note': 'Host inference timing; not FPGA throughput. --size is an explicit resolution change.'}, indent=2))


if __name__ == '__main__': main()
