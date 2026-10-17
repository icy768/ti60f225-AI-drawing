"""TARGET preview (not student output) for guides3 on fixed scenes. VG3 needs the AdaIN VG image for palette."""
import sys, pathlib, time, numpy as np
from PIL import Image
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from guides import ROOT, VGTeacher
from guides2 import ukiyoe2
from guides3 import vangogh3, ink3, vangogh4, ink4, vangogh5
if "--v5" in sys.argv: vangogh3, ink3 = vangogh5, ink4
if "--v4" in sys.argv: vangogh3, ink3 = vangogh4, ink4
from preview_guides import grid
t = VGTeacher(); rows = []
for n in sys.argv[2].split(','):
    rgb = np.array(Image.open(ROOT / 'data/test' / (n + '.png')).convert('RGB'))
    t0 = time.time(); v = (t(rgb) * 255).astype(np.uint8); a = vangogh3(rgb, v); c = ink3(rgb); print(n, round(time.time() - t0, 2), flush=True)
    rows.append((n, [rgb, a, ukiyoe2(rgb, n), c]))
grid(rows, ROOT / sys.argv[1])
