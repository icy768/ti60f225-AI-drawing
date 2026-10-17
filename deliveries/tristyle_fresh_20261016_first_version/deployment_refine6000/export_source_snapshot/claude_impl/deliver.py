"""Assemble first-version delivery: full-res 17-scene 3-style gallery from the delivered FP32 and INT8 models,
then write final_index.md linking every real artifact.
Usage: deliver.py <deployment_dir> <selected_ckpt> <run_name>"""
import sys, json, pathlib, time
import numpy as np, torch
from PIL import Image
HERE = pathlib.Path(__file__).resolve().parent; ROOT = HERE.parent; sys.path.insert(0, str(HERE))
from model import TriStyleV3, STYLES, model_for_state
from train import save_grid

def main():
    dep = ROOT / sys.argv[1]; ck = sys.argv[2]; run = sys.argv[3]
    torch.backends.quantized.engine = 'onednn'; torch.set_num_threads(4)
    state = torch.load(dep / 'tristyle_v3_fp32.pt', map_location='cpu', weights_only=False)['model']; fp = model_for_state(state).eval(); fp.load_state_dict(state)
    ts = torch.jit.load(str(dep / 'tristyle_v3_int8.ts')).eval()
    g = dep / 'gallery'; g.mkdir(exist_ok=True); rows_f = []; rows_i = []
    with torch.no_grad():
        for f in sorted((ROOT / 'data/test').glob('*.png')):
            im = Image.open(f).convert('RGB'); im = im.crop((0, 0, im.width // 8 * 8, im.height // 8 * 8)); a = np.array(im)
            x = torch.from_numpy(a).permute(2, 0, 1)[None].float() / 255; yf = []; yi = []
            for s in range(3):
                for tag, m, lst in (('fp32', fp, yf), ('int8', ts, yi)):
                    y = (m(x, s)[0].clamp(0, 1).permute(1, 2, 0).numpy() * 255).round().astype(np.uint8)
                    Image.fromarray(y).save(g / f'{f.stem}_{STYLES[s]}_{tag}.png'); lst.append(y)
            rows_f.append((f.stem + ' FP32', [a] + yf)); rows_i.append((f.stem + ' INT8', [a] + yi))
    save_grid(rows_f, dep / 'all17_three_styles_fp32.jpg'); save_grid(rows_i, dep / 'all17_three_styles_int8.jpg')
    print('gallery done', flush=True)

if __name__ == '__main__':
    main()
