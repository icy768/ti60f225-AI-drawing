"""CPU-free quick look at VG target variants (GPU AdaIN, small) on 4 scenes."""
import sys, pathlib, numpy as np
from PIL import Image
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from guides import ROOT, VGTeacher
from preview_guides import grid
t = VGTeacher(); rows = []
for n in ['person', 'sky_storm', 'architecture_street', 'plants_garden']:
    rgb = np.array(Image.open(ROOT / 'data/test' / (n + '.png')).convert('RGB'))
    rows.append((n, [rgb, t(rgb), t(rgb, mix=0.2, chroma_keep=0.25), t(rgb, mix=0.6, chroma_keep=0.6)]))
grid(rows, ROOT / 'reports/claude/vg_variants.jpg')
