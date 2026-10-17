"""v4 ukiyo-e / ink targets driven by ACTUAL public-domain artwork statistics (2026-10-17 03:30).

Supervisor 03:07/03:21: UK faces -> heavy dark fragments, generic cartoon; INK faces blank, dragon interior lost.
Changes:
 Ukiyo-e: palette = k-means of real Hokusai prints in data/references/ukiyoe (not hand-picked);
   regions = edge-preserving mean-shift segments of the photo (follow content, keep facial planes) mapped to
   that palette with luminance kept (no forced dark clusters); contours only on long, high-contrast region
   borders, thin (1-1.5px), never inside small regions; skin/flesh-like hues mapped to the print's pale flesh/
   paper tones; bokashi sky gradient kept.
 Ink: local contrast (CLAHE) before density so faces/eyes/mouth and interior form get ink; luminance
   histogram matched to real ink landscapes (data/references/ink central crops, mounting excluded);
   mid-scale wash-line layer (soft XDoG sigma 2.2) gives interior form; negative space only for large, smooth,
   very bright areas; wet accents only in large dark masses; deterministic flow-aligned bristle dry brush.
"""
import numpy as np, cv2, pathlib
from PIL import Image
from guides import xdog, _lab, ROOT
from guides2 import _keep_long
from guides3 import flow_field, lic

_PAL = {}
def reference_palette(k=14):
    if 'uk' in _PAL: return _PAL['uk']
    px = []
    for n in ['36490', '36492', '56214', '56216', '36500', '55736']:
        p = ROOT / 'data/references/ukiyoe' / (n + '.jpg')
        if not p.exists(): continue
        im = np.array(Image.open(p).convert('RGB')); h, w = im.shape[:2]
        im = im[int(h * .06):int(h * .94), int(w * .06):int(w * .94)]  # drop margins/borders
        im = cv2.resize(im, (256, int(256 * im.shape[0] / im.shape[1])), interpolation=cv2.INTER_AREA)
        px.append(_lab(im).reshape(-1, 3))
    px = np.concatenate(px).astype(np.float32)
    cv2.setRNGSeed(20261017)
    _, _, cent = cv2.kmeans(px, k, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, .5), 4, cv2.KMEANS_PP_CENTERS)
    _PAL['uk'] = cent[np.argsort(cent[:, 0])]; return _PAL['uk']

_INKHIST = {}
def reference_ink_cdf():
    if 'ink' in _INKHIST: return _INKHIST['ink']
    vals = []
    for n in ['45683', '49179', '49180', '51856', '51858', '49170', '39556']:
        p = ROOT / 'data/references/ink' / (n + '.jpg')
        if not p.exists(): continue
        g = np.array(Image.open(p).convert('L')).astype(np.float32) / 255; h, w = g.shape
        g = g[int(h * .12):int(h * .88), int(w * .12):int(w * .88)]  # central painting, no mounting
        g = (g - np.percentile(g, 1)) / (np.percentile(g, 99.5) - np.percentile(g, 1) + 1e-6)  # undo paper ageing
        vals.append(np.clip(g, 0, 1).ravel()[::7])
    v = np.sort(np.concatenate(vals)); _INKHIST['ink'] = v; return v

def match_hist(x, ref_sorted):
    """Map values of x so their distribution follows ref (monotone, content order preserved)."""
    flat = x.ravel(); order = np.argsort(flat); out = np.empty_like(flat)
    out[order] = ref_sorted[np.linspace(0, len(ref_sorted) - 1, len(flat)).astype(np.int64)]
    return out.reshape(x.shape)

def ukiyoe3(rgb, key='x'):
    h, w = rgb.shape[:2]; pal = reference_palette()
    # lift dark/low-contrast scenes (prints are light): CLAHE on L before segmentation
    lab0 = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB); lab0[..., 0] = cv2.createCLAHE(2.0, (8, 8)).apply(lab0[..., 0])
    rgb = cv2.cvtColor(lab0, cv2.COLOR_LAB2RGB)
    seg = cv2.pyrMeanShiftFiltering(rgb, 14, 34, maxLevel=2)
    for _ in range(3): seg = cv2.bilateralFilter(seg, 9, 40, 9)
    lab = _lab(seg)
    # map each pixel's chroma to the nearest print colour (chroma-weighted), keep own lightness
    d = ((lab[..., None, 1:] - pal[None, None, :, 1:]) ** 2).sum(-1) + 0.35 * (lab[..., None, 0] - pal[None, None, :, 0]) ** 2
    j = d.argmin(-1); P = pal[j]
    chroma = np.hypot(lab[..., 1] - 128, lab[..., 2] - 128)[..., None]
    wpal = np.clip(0.85 - chroma / 150, 0.4, 0.85)  # strong colours (flags, suits) stay closer to themselves
    ab = wpal * P[..., 1:] + (1 - wpal) * (128 + (lab[..., 1:] - 128) * 1.15)
    # skin protection: warm, moderately saturated, mid-light pixels -> print flesh tone, fine lightness kept
    skin = ((lab[..., 1] > 133) & (lab[..., 1] < 170) & (lab[..., 2] > 135) & (lab[..., 2] < 185) & (lab[..., 0] > 70)).astype(np.float32)
    skin = cv2.GaussianBlur(skin, (0, 0), 2)
    ab = ab * (1 - skin[..., None]) + np.array([142., 150.], np.float32) * skin[..., None]
    # flat value bands: quantise lightness to 5 print levels, lifted (prints are light)
    L = lab[..., 0]; Lq = np.round((L - 20) / 42.0) * 42.0 + 20; Lq = 0.85 * Lq + 0.15 * L; Lq = 50 + 0.78 * Lq
    Lq = Lq * (1 - skin) + (0.35 * L + 0.65 * 200) * skin  # faces: light flat flesh with retained planes
    out = np.stack([Lq, ab[..., 0], ab[..., 1]], -1)
    # flatten within mean-shift regions: median filter per channel removes residual shading
    flat = cv2.cvtColor(np.clip(out, 0, 255).astype(np.uint8), cv2.COLOR_LAB2RGB)
    flat = cv2.medianBlur(cv2.medianBlur(flat, 7), 5).astype(np.float32) / 255
    # bokashi sky
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255
    tex = cv2.GaussianBlur(np.abs(cv2.Laplacian(cv2.GaussianBlur(gray, (0, 0), 1.5), cv2.CV_32F)), (0, 0), 6)
    yy = np.linspace(0, 1, h, dtype=np.float32)[:, None]
    sky = cv2.GaussianBlur(((tex < 0.010) & (yy < 0.5) & (gray > 0.35)).astype(np.float32), (0, 0), 6)[..., None]
    blue = cv2.cvtColor(np.uint8([[pal[np.argmin(np.abs(pal[:, 2] - 105) + np.abs(pal[:, 0] - 90))]]]), cv2.COLOR_LAB2RGB)[0, 0].astype(np.float32) / 255
    grad = np.clip(1 - yy / 0.4, 0, 1)[..., None] ** 1.5
    flat = flat * (1 - sky * grad * 0.7) + blue * sky * grad * 0.7
    # contours: long, high-contrast borders of the flat image; thin; content edges from smoothed photo
    fg = cv2.cvtColor((flat * 255).astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32) / 255
    e1 = xdog(fg, sigma=1.0, p=26, eps=0.02, phi=10) < 0.5
    e2 = xdog(cv2.GaussianBlur(gray, (0, 0), 1.2), sigma=1.4, p=24, eps=0.02, phi=10) < 0.5
    gm = cv2.GaussianBlur(np.hypot(cv2.Sobel(fg, cv2.CV_32F, 1, 0), cv2.Sobel(fg, cv2.CV_32F, 0, 1)), (0, 0), 1)
    # region borders between DIFFERENT print colours (palette index changes), cleaned, plus content edges
    jm = cv2.medianBlur(j.astype(np.uint8), 5)
    pb = cv2.morphologyEx(jm, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)) > 0
    lines = _keep_long(((e1 | e2) & (gm > 0.08)) | pb, max(40, h * w // 5000)).astype(np.float32)
    lines = cv2.GaussianBlur(lines, (0, 0), 0.6) * (1 - 0.8 * sky[..., 0])
    lines = np.clip(lines * 1.3, 0, 0.9)[..., None]
    ink = cv2.cvtColor(np.uint8([[pal[0]]]), cv2.COLOR_LAB2RGB)[0, 0].astype(np.float32) / 255 * 0.8
    out = flat * (1 - lines) + ink * lines
    paper = np.array([0.96, 0.92, 0.83], np.float32)
    return np.clip(out * (0.9 + 0.1 * paper), 0, 1)

def ink5(rgb, key='x'):
    h, w = rgb.shape[:2]
    g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    cl = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(g).astype(np.float32) / 255
    gs = cv2.bilateralFilter(cl, 9, 0.12, 6)
    tx, ty = flow_field(gs, s_tensor=4.0, s_coarse=14.0)
    tone = match_hist(cv2.GaussianBlur(gs, (0, 0), 1.2), reference_ink_cdf())  # tonal distribution of real ink paintings
    dens = np.clip(1 - tone, 0, 1)
    wet = lic(cv2.GaussianBlur(dens, (0, 0), 1.6), tx, ty, 6)
    wash = sum(a * (0.5 + 0.5 * np.tanh((wet - t) * 7)) for a, t in ((0.18, 0.15), (0.20, 0.35), (0.20, 0.55), (0.16, 0.75)))
    big = cv2.GaussianBlur(dens, (0, 0), 6); acc = 0.5 + 0.5 * np.tanh((big - 0.82) * 10)
    wetink = np.maximum(acc * 0.3, cv2.GaussianBlur(acc, (0, 0), 4) * 0.2)
    # interior form: soft mid-scale wash lines
    mid = 1 - xdog(gs, sigma=2.2, p=18, eps=0.01, phi=6); mid = cv2.GaussianBlur(mid, (0, 0), 1.2) * 0.35
    # dry brush contour, thinner, bristle-broken
    u = gs + 1.5 * (gs - cv2.GaussianBlur(gs, (0, 0), 10))
    bristle = lic(0.5 + 0.5 * np.sin(2 * np.pi * 26 * u), tx, ty, 6)
    e = _keep_long((1 - xdog(gs, sigma=1.0, p=22, eps=0.01, phi=10)) > 0.5, max(20, h * w // 12000)).astype(np.float32)
    dry = np.clip(lic(e, tx, ty, 3) * 1.4, 0, 1) * np.clip(0.45 + 0.9 * bristle, 0, 1)
    det = np.abs(gs - cv2.GaussianBlur(gs, (0, 0), 2)); texm = np.clip((cv2.GaussianBlur(det, (0, 0), 8) - 0.02) * 20, 0, 1)
    cun = texm * np.clip((lic(0.5 + 0.5 * np.sin(2 * np.pi * 14 * u), tx, ty, 5) - 0.55) * 3, 0, 1) * (gs < cv2.GaussianBlur(gs, (0, 0), 20) + 0.03)
    # negative space: only LARGE smooth very bright areas (sky/water), not faces
    bright = (cv2.GaussianBlur(cl, (0, 0), 3) > 0.78).astype(np.uint8)
    n, cc, st, _ = cv2.connectedComponentsWithStats(bright, connectivity=8)
    big_ids = np.nonzero(st[:, cv2.CC_STAT_AREA] > h * w * 0.04)[0]; big_ids = big_ids[big_ids > 0]
    neg = cv2.GaussianBlur((np.isin(cc, big_ids) & (texm < 0.3)).astype(np.float32), (0, 0), 5)
    yy = np.linspace(0, 1, h, dtype=np.float32)[:, None]
    mist = np.clip(1 - (yy - 0.1) / 0.45, 0, 1) * 0.4 * (1 - texm) * neg
    total = np.clip(0.9 * wash + wetink + mid + 0.85 * dry + 0.5 * cun, 0, 0.93) * (1 - 0.85 * neg) * (1 - mist)
    paper = np.array([0.95, 0.93, 0.87], np.float32)[None, None]
    col = cv2.GaussianBlur(rgb.astype(np.float32) / 255, (0, 0), 5); tint = paper * (1 + 0.10 * (col - col.mean(2, keepdims=True)))
    return np.clip(tint * (1 - total[..., None]) + np.float32(0.08) * total[..., None], 0, 1)
