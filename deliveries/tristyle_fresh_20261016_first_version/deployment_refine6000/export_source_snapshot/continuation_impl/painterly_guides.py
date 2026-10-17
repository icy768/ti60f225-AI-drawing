"""Training-only multi-layer curved brush rendering and depth-organized ink/print guides.

Actual artwork palettes/CDF + content tangent fields + variable-width physical marks.
These are TARGETS, never inference postprocessing or evidence of student quality.
"""
import pathlib, sys
import cv2
import numpy as np
from PIL import Image
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'claude_impl'))
from guides import xdog, _lab
from guides3 import flow_field, lic
from guides4 import reference_palette, reference_ink_cdf, ukiyoe3, ink5
_VG = None


def vg_palette():
    global _VG
    if _VG is None:
        px = []
        for name in ('436532', '436534', '436535', 'starry_night'):
            im = Image.open(ROOT / 'data/references/vangogh' / (name + '.jpg')).convert('RGB')
            im.thumbnail((160, 160)); px.append(_lab(np.array(im)).reshape(-1, 3))
        cv2.setRNGSeed(20261017)
        _, _, _VG = cv2.kmeans(np.concatenate(px), 20, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 40, .5), 2, cv2.KMEANS_PP_CENTERS)
    return _VG


def trace(x, y, tx, ty, ref, color, radius, direction):
    h, w = tx.shape; pts = [[x, y]]; previous = None
    # More texture -> shorter marks; flat sky/large planes -> longer curved marks.
    for _ in range(7):
        ix, iy = min(w - 1, max(0, round(x))), min(h - 1, max(0, round(y)))
        v = np.array([tx[iy, ix], ty[iy, ix]], np.float32) * direction
        if previous is not None:
            if np.dot(v, previous) < 0: v = -v
            v = .55 * previous + .45 * v
        v /= max(np.linalg.norm(v), 1e-5); previous = v
        x += float(v[0]) * max(1., radius * .7); y += float(v[1]) * max(1., radius * .7)
        if x < 1 or y < 1 or x >= w - 1 or y >= h - 1: break
        if len(pts) >= 3 and np.linalg.norm(ref[int(y), int(x)] - color) > .24: break
        pts.append([x, y])
    return pts


def stamp(canvas, points, color, radius, alpha, ink=False, dry=False):
    p = np.rint(points).astype(np.int32); h, w = canvas.shape[:2]
    margin = int(radius * 1.4) + 3
    l, t = np.maximum(p.min(0) - margin, 0); r, b = np.minimum(p.max(0) + margin + 1, [w, h])
    if r <= l or b <= t or len(p) < 2: return
    p = p - [l, t]; mask = np.zeros((b - t, r - l), np.uint8)
    # Pressure tapers at ends, giving connected marks with nonuniform width.
    for i in range(1, len(p)):
        pressure = .55 + .45 * np.sin(np.pi * i / len(p))
        cv2.line(mask, tuple(p[i - 1]), tuple(p[i]), 255, max(1, round(radius * pressure * (1.1 if ink else 1.8))), cv2.LINE_AA)
    if dry:
        # Bristle channels follow the actual stroke; gaps are local, not global noise.
        for off in (-1, 1):
            q = p.copy(); q[:, 0] += off * max(1, round(radius * .22))
            cv2.polylines(mask, [q], False, 45, 1, cv2.LINE_AA)
    m = mask.astype(np.float32)[..., None] / 255 * alpha
    roi = canvas[t:b, l:r]; roi[:] = roi * (1 - m) + np.array(color, np.float32) * m
    if not ink:
        relief = (mask.astype(np.float32) - np.roll(mask.astype(np.float32), 1, axis=0)) / 255
        roi[:] = np.clip(roi + relief[..., None] * .035, 0, 1)


def brush_layers(ref, near, ink=False):
    h, w = ref.shape[:2]; gray = cv2.cvtColor((ref * 255).astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32) / 255
    tx, ty = flow_field(gray, s_tensor=3.5, s_coarse=14.)
    structure = cv2.GaussianBlur(np.abs(gray - cv2.GaussianBlur(gray, (0, 0), 1.5)), (0, 0), .8)
    if ink: canvas = np.broadcast_to(np.array([.95, .935, .89], np.float32), ref.shape).copy()
    else: canvas = cv2.GaussianBlur(ref, (0, 0), 12).copy()
    for layer, radius in enumerate((11., 6., 3., 1.3)):
        blurred = cv2.GaussianBlur(ref, (0, 0), max(.7, radius * .35))
        step = max(4, round(radius * (2.8 if ink and layer else 1.45))); starts = []
        error = np.linalg.norm(blurred - canvas, axis=2)
        for yy in range(step // 2, h, step):
            for xx in range(step // 2, w, step):
                ys = slice(max(0, yy - step // 2), min(h, yy + step // 2 + 1)); xs = slice(max(0, xx - step // 2), min(w, xx + step // 2 + 1))
                local = error[ys, xs]; iy, ix = np.unravel_index(local.argmax(), local.shape)
                y, x = ys.start + iy, xs.start + ix
                if layer == 3:
                    if local.max() > .11: starts.append((float(error[y, x]), x, y))
                elif layer == 0 or local.mean() > (.045 if ink else .025): starts.append((float(error[y, x]), x, y))
        # Coarse-to-fine, low-error first then strongest structural correction last.
        starts.sort()
        if layer >= 2 and len(starts) > h * w // 25: starts = starts[-(h * w // 25):]
        for _, x, y in starts:
            c = blurred[y, x]; r = radius * (.7 + .4 * near[y, x])
            if ink:
                density = float(1 - c.mean())
                if density < .035: continue
                if layer > 0 and structure[y, x] < .013 and density < .55: continue
                alpha = .55 if layer == 0 else (.10 + .40 * density) * (.35 + .65 * near[y, x])
            else: alpha = .90
            back = trace(x, y, tx, ty, blurred, c, r, -1)
            front = trace(x, y, tx, ty, blurred, c, r, 1)
            points = list(reversed(back[1:])) + front
            pigment = np.array([.06, .06, .055], np.float32) if ink and layer > 0 else c
            stamp(canvas, points, pigment, r * (.55 if ink and layer > 0 else 1.), alpha, ink, dry=ink and layer > 0 and near[y, x] > .35)
    return np.clip(canvas, 0, 1)


def vangogh8(rgb, near):
    ab = cv2.pyrMeanShiftFiltering(rgb, 12, 38, maxLevel=1)
    ab = cv2.bilateralFilter(ab, 9, 50, 8); lab = _lab(ab)
    lab[..., 1:] = 128 + (lab[..., 1:] - 128) * 1.35
    pal = vg_palette(); dd = ((lab[..., None, 1:] - pal[None, None, :, 1:]) ** 2).sum(-1) + .2 * (lab[..., None, 0] - pal[None, None, :, 0]) ** 2
    chosen = pal[dd.argmin(-1)]; lab = .85 * lab + .15 * chosen
    ref = cv2.cvtColor(lab.clip(0, 255).astype(np.uint8), cv2.COLOR_LAB2RGB).astype(np.float32) / 255
    out = brush_layers(ref, near, False)
    detail = rgb.astype(np.float32) / 255 - cv2.GaussianBlur(rgb.astype(np.float32) / 255, (0, 0), .8)
    # Only the narrow structural band is retained; no photographic shading overlay.
    return np.clip(out + detail * .35, 0, 1)


def ink8(rgb, near):
    g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY); g = cv2.createCLAHE(1.5, (8, 8)).apply(g).astype(np.float32) / 255
    gs = cv2.bilateralFilter(g, 9, .14, 7); mu = cv2.GaussianBlur(gs, (0, 0), 18)
    density = np.clip(.75 * (1 - gs) ** 1.2 + .7 * (mu - gs), 0, .95)
    # Relative depth controls visibility continuously; never threshold a face to white.
    visibility = .30 + .70 * np.sqrt(near)
    wash = (.55 * cv2.GaussianBlur(density, (0, 0), 2) + .45 * cv2.GaussianBlur(density, (0, 0), 7)) * visibility
    density = np.clip(.7 * density * visibility + .3 * wash, 0, .86)
    paper = np.array([.95, .935, .89], np.float32); black = np.array([.085, .082, .078], np.float32)
    ref = paper * (1 - density[..., None]) + black * density[..., None]
    out = brush_layers(ref.astype(np.float32), near, True)
    # Diffuse wet wash + irregular physical dry marks remain separate spatial layers.
    base = paper * (1 - .5 * wash[..., None]) + black * .5 * wash[..., None]
    wet_mix = (.1 + .35 * (1 - near))[..., None]
    out = out * (1 - wet_mix) + base * wet_mix
    fine = (1 - xdog(gs, sigma=.9, p=20, eps=.012, phi=8)) * (.12 + .30 * near)
    out = out * (1 - fine[..., None]) + black * fine[..., None]
    return np.clip(out, 0, 1)


def ukiyoe6(rgb, near):
    initial = (ukiyoe3(rgb) * 255).astype(np.uint8); lab = _lab(initial); pal = reference_palette()
    d = ((lab[..., None, 1:] - pal[None, None, :, 1:]) ** 2).sum(-1) + .2 * (lab[..., None, 0] - pal[None, None, :, 0]) ** 2
    labels = d.argmin(-1).astype(np.uint8); h, w = labels.shape
    for _ in range(2):
        for k in np.unique(labels):
            count, comp, stats, _ = cv2.connectedComponentsWithStats((labels == k).astype(np.uint8), 8)
            for i in range(1, count):
                if stats[i, cv2.CC_STAT_AREA] >= max(12, h * w // 1500): continue
                x, y, ww, hh = stats[i, :4]; l, t = max(0, x - 1), max(0, y - 1); r, b = min(w, x + ww + 1), min(h, y + hh + 1)
                m = (comp[t:b, l:r] == i).astype(np.uint8); ring = cv2.dilate(m, np.ones((3, 3), np.uint8)) - m
                vals = labels[t:b, l:r][ring > 0]
                if vals.size:
                    hist = np.bincount(vals, minlength=len(pal)).astype(float); hist[int(k)] = 0
                    labels[t:b, l:r][m > 0] = hist.argmax()
    flat = pal[labels].copy()
    # Skin regions use a light print plane; thin key lines below retain features.
    src = _lab(rgb); skin = ((src[..., 1] > 133) & (src[..., 1] < 173) & (src[..., 2] > 133) & (src[..., 2] < 183)).astype(np.float32)
    skin = cv2.GaussianBlur(skin, (0, 0), 1)
    flat[..., 0] = flat[..., 0] * (1 - skin) + (175 + .10 * src[..., 0]) * skin
    flat[..., 1:] = flat[..., 1:] * (1 - skin[..., None]) + np.array([140, 148]) * skin[..., None]
    base = cv2.cvtColor(flat.clip(0, 255).astype(np.uint8), cv2.COLOR_LAB2RGB).astype(np.float32) / 255
    g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255; gs = cv2.bilateralFilter(g, 9, .15, 8)
    line = 1 - xdog(gs, sigma=1.25, p=22, eps=.012, phi=7)
    line = cv2.GaussianBlur(line, (0, 0), .45) * .7
    fine = 1 - xdog(cv2.GaussianBlur(g, (0, 0), .45), sigma=.65, p=20, eps=.012, phi=8)
    sparse = np.clip(1 - cv2.GaussianBlur(np.abs(g - cv2.GaussianBlur(g, (0, 0), 1)), (0, 0), 4) * 18, 0, 1)
    line = np.maximum(line, fine * near * sparse * .5)
    black = np.array([.10, .13, .16]); out = base * (1 - line[..., None]) + black * line[..., None]
    # Restrained cloud/background decorative isophotes, limited to smooth far planes.
    smooth = cv2.GaussianBlur(g, (0, 0), 9); tex = cv2.GaussianBlur(np.abs(g - cv2.GaussianBlur(g, (0, 0), 2)), (0, 0), 5)
    deco = np.exp(-((np.sin(smooth * 30)) / .16) ** 2) * np.clip((.4 - near) * 2, 0, .35) * np.clip(1 - tex * 20, 0, 1)
    out = out * (1 - deco[..., None] * .2) + black * deco[..., None] * .2
    return np.clip(out, 0, 1)


def ink9(rgb, near):
    """Reference-CDF ink foundation, actual relative-depth wash/void hierarchy and flowing dry accents.
    Rejects the overpainted metallic-looking physical prototypes ink6-8.
    """
    base = ink5(rgb).astype(np.float32)
    paper = np.array([.96, .945, .90], np.float32); pigment = np.array([.075, .075, .07], np.float32)
    g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255
    gs = cv2.bilateralFilter(g, 9, .12, 7); mu = cv2.GaussianBlur(gs, (0, 0), 18)
    tex = cv2.GaussianBlur(np.abs(gs - cv2.GaussianBlur(gs, (0, 0), 2)), (0, 0), 5)
    density = np.clip((paper.mean() - base.mean(2)) / (paper.mean() - pigment.mean()), 0, 1)
    # Suppress fragmented dense micro-marks while retaining broad form masses.
    organized = .45 * density + .55 * cv2.GaussianBlur(density, (0, 0), 1.1)
    visibility = .40 + .60 * np.sqrt(near)
    wash = cv2.GaussianBlur(organized, (0, 0), 5) * (.16 + .18 * near)
    tx, ty = flow_field(gs, s_tensor=3.5, s_coarse=14.)
    edge = 1 - xdog(gs, sigma=1.05, p=22, eps=.012, phi=9)
    edge = lic(edge.astype(np.float32), tx, ty, 3)
    phase = gs + 1.2 * (gs - cv2.GaussianBlur(gs, (0, 0), 9))
    bristle = lic(.5 + .5 * np.sin(2 * np.pi * 23 * phase), tx, ty, 4)
    dry = edge * (.30 + .70 * bristle) * (.25 + .75 * near)
    d = np.clip(organized * visibility + wash * .15 + dry * .25, 0, .97)
    # Large smooth distant bright spaces only; actual depth keeps foreground faces out.
    candidate = ((near < .25) & (tex < .018) & (gs > .6)).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(candidate, 8)
    void = np.zeros_like(g)
    for i in range(1, count):
        if stats[i, cv2.CC_STAT_AREA] > g.size * .04: void[labels == i] = 1
    void = cv2.GaussianBlur(void, (0, 0), 8) * (1 - near) ** 2
    d = d * (1 - .50 * void)
    return np.clip(paper * (1 - d[..., None]) + pigment * d[..., None], 0, 1)


def render_all(rgb, near):
    return [vangogh8(rgb, near), ukiyoe6(rgb, near), ink9(rgb, near)]
