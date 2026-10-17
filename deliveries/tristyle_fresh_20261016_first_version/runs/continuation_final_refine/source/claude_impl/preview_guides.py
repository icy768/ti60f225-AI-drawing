import sys, pathlib, time
import numpy as np, cv2
from PIL import Image, ImageDraw
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from guides import ROOT, VGTeacher
if "--v1" in sys.argv:
    from guides import ukiyoe, ink
else:
    from guides2 import ukiyoe2 as ukiyoe, ink2 as ink

def grid(rows, dest, W=320):
    H = 240
    c = Image.new('RGB', (W * 4, (H + 16) * len(rows)), 'white'); d = ImageDraw.Draw(c)
    for i, (name, ims) in enumerate(rows):
        for j, im in enumerate(ims):
            p = Image.fromarray((np.clip(im, 0, 1) * 255).astype(np.uint8) if im.dtype != np.uint8 else im); p.thumbnail((W, H))
            c.paste(p, (j * W, i * (H + 16)))
            d.text((j * W + 3, i * (H + 16) + H + 2), f'{name} {["input","vangogh","ukiyoe","ink"][j]}', fill='black')
    c.save(dest, quality=90)

if __name__ == '__main__':
    out = ROOT / sys.argv[1]; out.parent.mkdir(parents=True, exist_ok=True)
    vg = VGTeacher(); rows = []
    files = sorted((ROOT / 'data/test').glob('*.png'))
    if len(sys.argv) > 2: files = [f for f in files if f.stem in sys.argv[2].split(',')]
    for f in files:
        rgb = np.array(Image.open(f).convert('RGB'))
        t = time.time(); a = vg(rgb); b = ukiyoe(rgb, f.stem); c = ink(rgb, f.stem)
        print(f.stem, rgb.shape, round(time.time() - t, 2), flush=True)
        rows.append((f.stem, [rgb, a, b, c]))
    grid(rows, out)
