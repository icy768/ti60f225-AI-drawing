"""TARGET preview for guides4 on VALIDATION photos with people (COCO annotations) + Sintel TRAINING-segment frames.
Never uses fixed test scenes or held-out video (>=640). Output columns: input | ukiyoe2 (old) | ukiyoe3 | ink34-like old | ink5."""
import sys, json, pathlib, numpy as np, cv2
from PIL import Image, ImageDraw
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from guides import ROOT
from guides2 import ukiyoe2
from guides3 import ink3, ink4
from guides4 import ukiyoe3, ink5
T = ROOT / 'data/claude_targets'
ann = json.loads((ROOT / 'data/raw/instances_val2017.json').read_text())
person = {a['image_id'] for a in ann['annotations'] if a['category_id'] == 1 and a['area'] > 15000}
stems = sorted(p.stem for p in (T / 'content/validation').glob('*.png'))
sel = [s for s in stems if int(s) in person][:5] + [s for s in stems if int(s) not in person][:2]
rows = []
for s in sel:
    rgb = np.array(Image.open(T / 'content/validation' / (s + '.png')).convert('RGB'))
    old_ink = (0.5 * ink3(rgb) + 0.5 * ink4(rgb))
    rows.append((s, [rgb, ukiyoe2(rgb, s), ukiyoe3(rgb, s), old_ink, ink5(rgb, s)]))
cap = cv2.VideoCapture(str(ROOT / 'data/video/sintel_trailer-480p.mp4'))
for fr in [150, 330, 520]:  # inside training segment (63-624)
    cap.set(cv2.CAP_PROP_POS_FRAMES, fr); ok, bgr = cap.read(); rgb = cv2.resize(bgr, (480, 216))[:, :, ::-1].copy()
    rows.append((f'sintel_train_{fr}', [rgb, ukiyoe2(rgb, str(fr)), ukiyoe3(rgb, str(fr)), 0.5 * ink3(rgb) + 0.5 * ink4(rgb), ink5(rgb, str(fr))]))
W, H = 288, 216; c = Image.new('RGB', (W * 5, (H + 14) * len(rows)), 'white'); d = ImageDraw.Draw(c)
for i, (n, ims) in enumerate(rows):
    for j, im in enumerate(ims):
        p = Image.fromarray((np.clip(im, 0, 1) * 255).astype(np.uint8) if im.dtype != np.uint8 else im); p.thumbnail((W, H)); c.paste(p, (j * W, i * (H + 14)))
        d.text((j * W + 3, i * (H + 14) + H + 1), f"{n} {['input', 'ukiyoe2(old)', 'ukiyoe3', 'ink34(old)', 'ink5'][j]}", fill='black')
c.save(ROOT / sys.argv[1], quality=88); print('saved', sel)
