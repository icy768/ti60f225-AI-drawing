"""v2 NPR targets after supervisor review of guides_v4 (TARGET previews, not student results).
Ukiyo-e: island merge, contours only on colour-distinct region borders + long structural edges.
Ink: explicit wet accent / light wash / directional dry brush / texture strokes / mist hierarchy.
"""
import numpy as np, cv2
from guides import seed_of, smooth_noise, xdog, _lab, PAL_LAB, UKIYOE_PALETTE, ROOT, VGTeacher

def _merge_small(lbl, K, min_area):
    keep = np.ones(lbl.shape, bool)
    for k in range(K):
        n, cc, st, _ = cv2.connectedComponentsWithStats((lbl == k).astype(np.uint8), connectivity=4)
        small = np.nonzero(st[1:, cv2.CC_STAT_AREA] < min_area)[0] + 1
        if len(small): keep &= ~np.isin(cc, small)
    if keep.all(): return lbl
    votes = np.stack([cv2.boxFilter(((lbl == k) & keep).astype(np.float32), -1, (31, 31), normalize=False) for k in range(K)])
    return np.where(keep, lbl, votes.argmax(0).astype(np.uint8))

def _keep_long(mask, min_area):
    n, cc, st, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    good = np.nonzero(st[:, cv2.CC_STAT_AREA] >= min_area)[0]; good = good[good > 0]
    return np.isin(cc, good)

def ukiyoe2(rgb, key='x'):
    rng = np.random.default_rng(seed_of('u' + key)); h, w = rgb.shape[:2]
    small = cv2.pyrMeanShiftFiltering(rgb, 12, 32, maxLevel=1)
    for _ in range(3): small = cv2.bilateralFilter(small, 9, 45, 9)
    lab = _lab(small).reshape(-1, 3); K = 8
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0); cv2.setRNGSeed(seed_of('k' + key) % 2 ** 31)
    _, _, cent = cv2.kmeans(lab[::7].copy(), K, None, crit, 2, cv2.KMEANS_PP_CENTERS)
    lbl = ((lab[:, None, :] - cent[None]) ** 2).sum(-1).argmin(1).reshape(h, w).astype(np.uint8)
    lbl = cv2.medianBlur(lbl, 9)
    lbl = _merge_small(lbl, K, max(60, h * w // 900))
    out_c = []
    for c in cent:
        dd = (((PAL_LAB[:, 1:] - c[1:]) ** 2).sum(-1) + 0.15 * (PAL_LAB[:, 0] - c[0]) ** 2)
        if np.hypot(c[1] - 128, c[2] - 128) < 14:
            fam = [0, 1, 2, 3] if c[2] < 127 else [4, 5, 11, 12]
            dd = dd + 1e6 * ~np.isin(np.arange(len(PAL_LAB)), fam)
        j = dd.argmin(); chroma = np.hypot(c[1] - 128, c[2] - 128); wpal = 0.6 if chroma < 14 else 0.3
        m = c.copy(); m[1:] = wpal * PAL_LAB[j, 1:] + (1 - wpal) * (128 + (c[1:] - 128) * 1.2); m[0] = 50 + 0.78 * c[0]
        out_c.append(m)
    out_c = np.array(out_c, np.float32); flatlab = out_c[lbl]
    flat = cv2.cvtColor(np.clip(flatlab, 0, 255).astype(np.uint8), cv2.COLOR_LAB2RGB).astype(np.float32) / 255
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255
    tex = cv2.GaussianBlur(np.abs(cv2.Laplacian(cv2.GaussianBlur(gray, (0, 0), 1.5), cv2.CV_32F)), (0, 0), 6)
    top = list(set(np.unique(lbl[: max(2, h // 20)]).tolist())); yy = np.linspace(0, 1, h, dtype=np.float32)[:, None]
    sky = cv2.GaussianBlur((np.isin(lbl, top) & (tex < 0.012) & (yy < 0.6)).astype(np.float32), (0, 0), 3)[..., None]
    grad = np.clip(1 - yy / 0.45, 0, 1)[..., None] ** 1.5
    flat = flat * (1 - sky * grad * 0.75) + UKIYOE_PALETTE[1] / 255 * sky * grad * 0.75
    fl = cv2.GaussianBlur(flatlab, (0, 0), 1.0)
    dE = np.sqrt(sum(cv2.Sobel(fl[..., c], cv2.CV_32F, 1, 0) ** 2 + cv2.Sobel(fl[..., c], cv2.CV_32F, 0, 1) ** 2 for c in range(3))) / 4
    bnd = (cv2.morphologyEx(lbl, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)) > 0) & (cv2.dilate(dE, np.ones((3, 3))) > 14) & (sky[..., 0] < 0.5)
    sg = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255
    e = _keep_long(xdog(sg, sigma=1.3, p=24, eps=0.015, phi=8) < 0.5, max(40, (h * w) // 6000))
    lines = _keep_long(bnd | e, max(30, (h * w) // 8000)).astype(np.float32)
    lines = np.clip(cv2.GaussianBlur(lines, (0, 0), 0.7) * 1.6, 0, 1)[..., None]
    out = flat * (1 - lines) + np.array([30, 32, 44], np.float32) / 255 * lines
    grain = smooth_noise(h, w, 2, rng) * 0.010 + cv2.GaussianBlur(rng.standard_normal((h, w)).astype(np.float32), (0, 0), 0.7) * 0.010
    out = (out + grain[..., None]) * (0.92 + 0.08 * np.array([0.95, 0.91, 0.82], np.float32))
    return np.clip(out, 0, 1)

def ink2(rgb, key='x'):
    rng = np.random.default_rng(seed_of('i' + key)); h, w = rgb.shape[:2]
    g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255
    gs = cv2.bilateralFilter(g, 9, 0.12, 6); mu = cv2.GaussianBlur(gs, (0, 0), 25)
    dens = np.clip(0.8 * (1 - gs) ** 1.4 + 0.9 * (mu - gs), 0, 1)
    n1 = smooth_noise(h, w, 5, rng); n2 = smooth_noise(h, w, 28, rng)
    wet = cv2.GaussianBlur(dens, (0, 0), 2.2) + 0.03 * n1 + 0.02 * n2
    wash = 0.20 * (0.5 + 0.5 * np.tanh((wet - 0.15) * 8)) + 0.25 * (0.5 + 0.5 * np.tanh((wet - 0.38) * 8)) + 0.15 * (0.5 + 0.5 * np.tanh((wet - 0.55) * 8))
    wash = cv2.GaussianBlur(wash, (0, 0), 2.0)
    acc = 0.5 + 0.5 * np.tanh((cv2.GaussianBlur(dens, (0, 0), 4) - 0.78) * 12)  # concentrated wet ink accents
    wetink = np.maximum(acc * 0.45, cv2.GaussianBlur(acc, (0, 0), 3.5) * 0.3)  # bleed rim
    e = _keep_long((1 - xdog(gs, sigma=1.4, p=22, eps=0.01, phi=10)) > 0.5, max(25, h * w // 9000)).astype(np.float32)
    e = cv2.dilate(e, np.ones((2, 2), np.uint8))
    gy = cv2.Sobel(gs, cv2.CV_32F, 0, 1, ksize=5); gx = cv2.Sobel(gs, cv2.CV_32F, 1, 0, ksize=5)
    r = rng.random((h, w)).astype(np.float32)
    sh = cv2.blur(r, (13, 1)); sv = cv2.blur(r, (1, 13))
    sd1 = cv2.filter2D(r, -1, np.eye(9, dtype=np.float32) / 9); sd2 = cv2.filter2D(r, -1, np.fliplr(np.eye(9, dtype=np.float32)) / 9)
    ang = (np.degrees(np.arctan2(gy, gx)) + 180) % 180  # gradient angle; streak along the edge tangent
    st = np.where((ang < 22.5) | (ang >= 157.5), sv, np.where(ang < 67.5, sd2, np.where(ang < 112.5, sh, sd1)))
    dry = e * np.clip((st - 0.40) * 7, 0.15, 1)
    det = np.abs(gs - cv2.GaussianBlur(gs, (0, 0), 2)); texm = np.clip((cv2.GaussianBlur(det, (0, 0), 8) - 0.015) * 25, 0, 1)
    dots = cv2.GaussianBlur(cv2.dilate((rng.random((h, w)) < 0.035).astype(np.float32), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))), (0, 0), 0.7)
    cun = texm * np.clip(0.7 * dots * (gs < mu + 0.02) + 1.2 * det * (gs < mu), 0, 1)
    yy = np.linspace(0, 1, h, dtype=np.float32)[:, None]
    mist = np.clip(1 - (yy - 0.12) / 0.5, 0, 1) * 0.5 * (1 - 0.6 * texm) * (0.75 + 0.25 * n2.clip(-1, 1))
    neg = np.clip((gs - 0.70) * 3.0, 0, 1) * (1 - texm)
    total = np.clip(0.85 * wash + wetink + 0.95 * dry + 0.6 * cun, 0, 1) * (1 - mist) * (1 - 0.85 * neg)
    paper = np.array([0.95, 0.93, 0.87], np.float32)
    fib = cv2.GaussianBlur(rng.standard_normal((h, w)).astype(np.float32), (0, 0), 0.8) * 0.012 + smooth_noise(h, w, 40, rng) * 0.012
    pap = paper[None, None] + fib[..., None]
    col = cv2.GaussianBlur(rgb.astype(np.float32) / 255, (0, 0), 5); tint = pap * (1 + 0.12 * (col - col.mean(2, keepdims=True)))
    return np.clip(tint * (1 - total[..., None]) + np.float32(0.08) * total[..., None], 0, 1)
