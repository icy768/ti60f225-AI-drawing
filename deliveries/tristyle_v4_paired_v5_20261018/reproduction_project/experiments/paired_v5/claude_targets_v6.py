"""Claude takeover P1 targets v6: strictly LOCAL deterministic three-style teachers (PLAN v3 §4).

Every operator uses only a <=60px neighbourhood of the input, or GLOBAL CONSTANTS computed once
(palette from curated ukiyo-e prints + canonical hues; ink tone curve from curated ink references and the
same fixed 12-validation luma quantiles Codex used). No region merging, no per-image CDF, no component
ranking, no absolute image position, no coordinate RNG. Outputs are OFFLINE TEACHERS, never student results.
Far-fade uses a LOCAL sharpness proxy, not monocular depth (depth needs whole-image context, violates §4.0).
"""
from pathlib import Path
import argparse, hashlib, json, re, sys, time
import cv2, numpy as np
from PIL import Image, ImageDraw

ROOT = Path(r'D:\fpga\tristyle_v4_20261017')
V3 = Path(r'D:\fpga\tristyle_fresh_20261016')
STYLES = ('vangogh', 'ukiyoe', 'ink')
VERSION = 'claude_targets_v6_04'
P = {
    'version': VERSION,
    'ukiyoe': {'bilateral': [7, 0.10, 4.0], 'bilateral_passes': 2, 'meanshift_sp': 6, 'meanshift_sr': 14,
               'palette_kmeans': 12, 'lab_L_weight': 0.55, 'mode_passes': [11, 11, 7], 'shade_dL': 11.0,
               'L_gamma': 0.62, 'boundary_purity': 0.30, 'sumi_penalty': 220.0,
               'shade_factor': 0.80, 'contour_deltaE': 18.0, 'xdog_sigma': 1.2, 'xdog_eps': 0.016,
               'coherence_min': 0.60, 'texture_density_max': 0.22, 'contour_alpha': 0.92,
               'contour_rgb': [0.13, 0.15, 0.24], 'bokashi_window_px': 31, 'bokashi_strength': 0.45,
               'paper_rgb': [0.94, 0.90, 0.80], 'paper_mix': 0.05, 'paper_grain': 0.03},
    'ink': {'bilateral': [9, 0.12, 5.0], 'tone_gamma': 1.35, 'line_bleed': 1.2, 'fine_line_weight': 0.45,
            'levels': [0.0, 0.28, 0.55, 0.85], 'level_sigma': 0.06,
            'level_mix': 0.85, 'wash_blur': 1.6, 'wet_rim': 0.6, 'blank_var': 0.004, 'blank_strength': 0.85,
            'far_sharp_scale': 0.02, 'far_fade': 0.35, 'dog1': [1.0, 1.6, 0.012], 'dog2': [2.0, 3.2, 0.018],
            'line_contrast_scale': 0.15, 'dry_break': 0.7, 'texture_density_max': 0.35,
            'texture_thin': 0.4, 'cun_len': 4, 'cun_strength': 0.22, 'face_wash': 0.7,
            'paper_rgb': [0.96, 0.94, 0.89], 'ink_rgb': [0.10, 0.105, 0.115], 'paper_grain': 0.02},
    'vangogh': {'tensor_sigma': 6.0, 'kuwahara_radius': 6, 'hue_anchors': [10, 48, 140, 220], 'hue_pull': 0.55,
                'sat_gain': 1.5, 'min_sat': 0.18, 'shadow_hue': 230, 'highlight_hue': 50, 'tone_pull': 0.3,
                'lic_short': 6, 'lic_long': 22, 'noise_blur': 1.2, 'detail_scale': 0.03, 'stroke_amp': 0.16,
                'amp_floor': 0.012, 'grey_tint_sat': 0.10,
                'stroke_sat': 0.10, 'emboss': 0.05, 'face_scale': 0.5, 'outline_alpha': 0.35,
                'outline_rgb': [0.10, 0.14, 0.30]},
}
CANON_UK = [  # traditional woodblock hues guaranteeing coverage (RGB 0-1)
    [0.16, 0.22, 0.36], [0.20, 0.36, 0.56], [0.62, 0.74, 0.82], [0.80, 0.86, 0.86],  # indigo, prussian, sky, pale
    [0.20, 0.33, 0.24], [0.40, 0.55, 0.32], [0.66, 0.72, 0.42],                      # 3 greens
    [0.78, 0.60, 0.30], [0.80, 0.30, 0.20], [0.93, 0.80, 0.66], [0.94, 0.90, 0.80],  # ochre vermilion flesh paper
    [0.12, 0.11, 0.12], [0.48, 0.32, 0.22], [0.55, 0.55, 0.52], [0.88, 0.66, 0.66], [0.88, 0.80, 0.62]]


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def blur(a, s): return cv2.GaussianBlur(a, (0, 0), s, borderType=cv2.BORDER_REFLECT_101) if s > 0 else a
def gray(a): return (a @ np.array([.299, .587, .114], np.float32)).astype(np.float32)
def unit(a): return np.clip(a, 0, 1).astype(np.float32)
def lnorm(a, s): return np.tanh(a / (np.sqrt(blur(a * a, s)) + 4e-3))
def to_lab(rgb): return cv2.cvtColor(unit(rgb), cv2.COLOR_RGB2LAB)
def lab2rgb(lab): return cv2.cvtColor(lab.astype(np.float32).reshape(-1, 1, 3), cv2.COLOR_LAB2RGB).reshape(-1, 3)


def tensor(g, s):
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0) / 8; gy = cv2.Sobel(g, cv2.CV_32F, 0, 1) / 8
    xx, yy, xy = blur(gx * gx, s), blur(gy * gy, s), blur(gx * gy, s)
    theta = .5 * np.arctan2(2 * xy, xx - yy) + np.pi / 2
    coh = np.sqrt((xx - yy) ** 2 + 4 * xy * xy) / (xx + yy + 1e-6)
    return np.cos(theta).astype(np.float32), np.sin(theta).astype(np.float32), coh.astype(np.float32), np.sqrt(xx + yy)


def lic(src, tx, ty, length):
    h, w = src.shape; yy, xx = np.mgrid[:h, :w].astype(np.float32); tot = src.copy(); wt = np.ones_like(src)
    for d in (-1, 1):
        px, py = xx.copy(), yy.copy(); vx, vy = tx.copy(), ty.copy()
        for j in range(1, length + 1):
            nx = cv2.remap(tx, px, py, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT_101)
            ny = cv2.remap(ty, px, py, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT_101)
            sg = np.where(nx * vx + ny * vy >= 0, 1., -1.).astype(np.float32); vx, vy = nx * sg, ny * sg
            px += d * vx; py += d * vy; ww = 1 - j / (length + 1)
            tot += cv2.remap(src, px, py, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT_101) * ww; wt += ww
    return tot / wt
def build_assets():
    """GLOBAL CONSTANTS only: ukiyo-e palette (k-means of curated prints + canonical hues), ink tone curve."""
    man_p = ROOT / 'data/curated_references.json'; man = json.loads(man_p.read_text(encoding='utf-8'))
    cor_p = ROOT / 'data/curated_references_v3.json'
    cor = {r['id']: r for r in json.loads(cor_p.read_text(encoding='utf-8'))['references']}
    pal, ink, sources = [], [], []
    for r in man['references']:
        if not r.get('use_for_training', True) or r['style'] not in ('ukiyoe', 'ink'): continue
        p = ROOT / r['path']; assert sha(p) == r['sha256']
        a = np.asarray(Image.open(p).convert('RGB'), np.float32) / 255; h, w = a.shape[:2]
        valid = np.zeros((h, w), np.uint8); l, t, rr, b = r['painting_ROI_normalized']
        valid[round(t * h):round(b * h), round(l * w):round(rr * w)] = 1
        exc = r['exclusion_regions_normalized'] + cor.get(r['id'], {}).get('exclusion_regions_normalized', [])
        for l, t, rr, b in exc: valid[int(t * h):int(np.ceil(b * h)), int(l * w):int(np.ceil(rr * w))] = 0
        px = a[valid.astype(bool)]; px = px[::max(1, len(px) // 12000)][:12000]
        if r['style'] == 'ukiyoe': pal.append(px)
        else:
            lum = gray(px); lo, hi = np.quantile(lum, [.01, .95])
            ink.append(np.clip(.04 + .94 * (lum - lo) / max(.1, hi - lo), .02, .99))
        sources.append({'id': r['id'], 'style': r['style'], 'sha256': sha(p), 'samples': int(len(px))})
    cv2.setRNGSeed(20261106)
    z = to_lab(np.concatenate(pal).reshape(-1, 1, 3)).reshape(-1, 3).astype(np.float32)
    _, _, km = cv2.kmeans(z, P['ukiyoe']['palette_kmeans'], None,
                          (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 60, .05), 1, cv2.KMEANS_PP_CENTERS)
    canon = to_lab(np.array(CANON_UK, np.float32).reshape(-1, 1, 3)).reshape(-1, 3)
    palette = list(canon)
    for c in km:  # add print clusters that are not near-duplicates of canonical hues
        if min(np.linalg.norm(c - q) for q in palette) > 10: palette.append(c)
    palette = np.array(palette, np.float32)
    qs = np.linspace(0, 1, 257); ink_vals = np.quantile(np.concatenate(ink), qs).astype(np.float32)
    # Same fixed 12-validation luma quantiles as Codex targets_10-12 (a constant, not per-image).
    files = sorted((V3 / 'data/claude_targets/content/validation').glob('*.png'))
    ids = np.linspace(0, len(files) - 1, 12).round().astype(int); cl = []
    for i in ids:
        g = gray(np.asarray(Image.open(files[i]).convert('RGB'), np.float32) / 255).ravel()
        cl.append(g[::max(1, len(g) // 12000)][:12000])
    src_vals = np.quantile(np.concatenate(cl), qs).astype(np.float32)
    return {'palette_lab': palette.tolist(), 'palette_rgb': unit(lab2rgb(palette)).tolist(),
            'canonical_hues': len(CANON_UK), 'ink_quantiles': ink_vals.tolist(), 'source_luma_quantiles': src_vals.tolist(),
            'sources': sources, 'manifest_sha256': sha(man_p), 'extra_exclusions_sha256': sha(cor_p)}


def face_mask(a, subject):
    r, g, b = a.transpose(2, 0, 1); skin = (r > .20) & (r > g * .95) & (g > b * .95) & (r - b > .035) & (r - g < .30)
    sup = subject if subject.max() > .05 else np.full_like(subject, .75)
    return unit(blur(skin.astype(np.float32) * sup, 3))


def kuwahara(a, tx, ty, radius):
    h, w = a.shape[:2]; yy, xx = np.mgrid[:h, :w].astype(np.float32); cands, vars_ = [], []
    for sx, sy in ((-1, -1), (-1, 1), (1, -1), (1, 1)):
        m = np.zeros_like(a); sq = np.zeros_like(a); n = 0
        for i in range(0, radius + 1, 2):
            for j in range(0, radius + 1, 2):
                ox = tx * i * sx - ty * j * sy; oy = ty * i * sx + tx * j * sy
                s = cv2.remap(a, xx + ox, yy + oy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT_101)
                m += s; sq += s * s; n += 1
        m /= n; cands.append(m); vars_.append((sq / n - m * m).sum(-1))
    wts = np.exp(-np.stack(vars_) / .004); wts /= wts.sum(0, keepdims=True) + 1e-8
    return (np.stack(cands) * wts[..., None]).sum(0)


def mode_filter(lbl, k, n):
    best = np.zeros(lbl.shape, np.float32) - 1; out = lbl.copy()
    for c in np.unique(lbl):
        cnt = cv2.boxFilter((lbl == c).astype(np.float32), -1, (k, k), normalize=False, borderType=cv2.BORDER_REFLECT_101)
        better = cnt > best; out[better] = c; best[better] = cnt[better]
    return out


def xdog(g, s, k=1.6, eps=.01):
    d = blur(g, s) - blur(g, s * k)
    return unit(-d / eps)  # dark side of edges in [0,1]


def ukiyoe(a, subject, A):
    c = P['ukiyoe']; d, sc, ss = c['bilateral']; x = a.copy()
    for _ in range(c['bilateral_passes']): x = cv2.bilateralFilter(x, d, sc, ss)
    ms = cv2.pyrMeanShiftFiltering((unit(x) * 255).round().astype(np.uint8), c['meanshift_sp'], c['meanshift_sr'], maxLevel=0)
    lab = to_lab(ms.astype(np.float32) / 255); pal = np.array(A['palette_lab'], np.float32)
    lab[..., 0] = 100 * (np.clip(lab[..., 0], 0, 100) / 100) ** c['L_gamma']  # fixed pixelwise lift: prints have few blacks
    wv = np.array([c['lab_L_weight'], 1, 1], np.float32)
    dist = (((lab[:, :, None, :] - pal[None, None]) * wv) ** 2).sum(-1)
    dist = dist + c['sumi_penalty'] * (pal[:, 0] < 25)[None, None].astype(np.float32)  # sumi black only for true blacks
    lbl = dist.argmin(-1).astype(np.int32)
    face = face_mask(a, subject)
    dark = pal[:, 0] < 45; flesh = int(np.argmin(((pal - to_lab(np.array([[[.93, .80, .66]]], np.float32))[0, 0]) ** 2).sum(-1)))
    lbl = np.where((face > .4) & dark[lbl], flesh, lbl)  # no black face masses
    for k in c['mode_passes']: lbl = mode_filter(lbl, k, len(pal))
    out_lab = pal[lbl].copy()
    shade = (blur(lab[..., 0], 2) < out_lab[..., 0] - c['shade_dL'])  # at most 2 value levels per block
    out_lab[..., 0] = np.where(shade, out_lab[..., 0] * c['shade_factor'], out_lab[..., 0])
    rgb = unit(cv2.cvtColor(out_lab.astype(np.float32), cv2.COLOR_LAB2RGB))
    # bokashi: sky-coloured blocks darken toward prussian where more sky lies BELOW (local one-sided window)
    sky = ((pal[:, 2] < -8) & (pal[:, 0] > 55))[lbl].astype(np.float32); W = c['bokashi_window_px']
    kern = np.zeros((2 * W + 1, 1), np.float32); kern[W:, 0] = 1 / (W + 1)
    below = cv2.filter2D(sky, -1, kern, anchor=(0, W), borderType=cv2.BORDER_REFLECT_101)
    prussian = np.array([.20, .36, .56], np.float32); bk = (sky * below * c['bokashi_strength'])[..., None]
    rgb = rgb * (1 - bk) + prussian * bk
    # contours: palette-boundary dE>thr + long coherent XDoG edges; suppressed in busy texture
    pl = pal[lbl]; de = np.zeros(lbl.shape, np.float32)
    for dy, dx in ((0, 1), (1, 0)):
        sh = np.roll(pl, (-dy, -dx), (0, 1)); de = np.maximum(de, np.linalg.norm(pl - sh, axis=-1))
    bnd = (de > c['contour_deltaE']).astype(np.float32)
    # drop boundaries of tiny specks: own label must occupy a reasonable share of the 9x9 window
    own = np.zeros(lbl.shape, np.float32)
    for cc in np.unique(lbl):
        m = lbl == cc; own[m] = cv2.blur(m.astype(np.float32), (9, 9), borderType=cv2.BORDER_REFLECT_101)[m]
    bnd = bnd * (own > c['boundary_purity'])
    g = gray(unit(x)); tx, ty, coh, _ = tensor(g, 3)
    e = xdog(g, c['xdog_sigma'], eps=c['xdog_eps']); dens = blur((e > .5).astype(np.float32), 6)
    longe = e * (coh > c['coherence_min']) * (dens < c['texture_density_max'])
    fe = xdog(g, .8, eps=.008) * face  # finer feature lines inside faces
    line = unit(np.maximum(np.maximum(bnd * (dens < .45 + face), longe), fe))
    line = unit(blur(cv2.dilate(line, np.ones((2, 2), np.uint8)), .6) * 1.4) * c['contour_alpha']
    rgb = rgb * (1 - line[..., None]) + np.array(c['contour_rgb'], np.float32) * line[..., None]
    gr = gray(a); grain = lnorm(gr - blur(gr, 1.0), 3) * c['paper_grain']
    rgb = rgb * (1 - c['paper_mix']) + np.array(c['paper_rgb'], np.float32) * c['paper_mix'] + grain[..., None] * .5
    return unit(rgb), {'regions': 'local palette+mode filter', 'palette_size': len(pal)}
def ink(a, subject, A):
    c = P['ink']; g = gray(a)
    tone = np.interp(g, np.array(A['source_luma_quantiles']), np.array(A['ink_quantiles'])).astype(np.float32)  # fixed curve
    tone = tone ** c['tone_gamma']  # deeper mid-tones -> more visible wash (fixed, pixelwise)
    d, sc, ss = c['bilateral']; t = cv2.bilateralFilter(tone, d, sc, ss); dens = 1 - t
    lv = np.array(c['levels'], np.float32); wq = np.exp(-(dens[..., None] - lv) ** 2 / (2 * c['level_sigma'] ** 2))
    q = (wq * lv).sum(-1) / (wq.sum(-1) + 1e-6); dens = c['level_mix'] * q + (1 - c['level_mix']) * dens
    wash = blur(dens, c['wash_blur']); wash = unit(wash + c['wet_rim'] * np.clip(wash - blur(wash, 4), 0, None))
    var = blur(g * g, 6) - blur(g, 6) ** 2  # blank paper: smooth AND bright (sky/water/mist)
    blank = unit((1 - var / c['blank_var'])) * unit((g - .55) / .25)
    sharp = np.sqrt(blur((g - blur(g, 1)) ** 2, 8)); far = unit(1 - sharp / c['far_sharp_scale'])  # local proxy
    wash = wash * (1 - c['blank_strength'] * blank) * (1 - c['far_fade'] * far)
    s1, k1, e1 = c['dog1']; s2, k2, e2 = c['dog2']
    l1 = xdog(g, s1, k1 / s1, e1); l2 = xdog(g, s2, k2 / s2, e2)
    contrast = unit(np.sqrt(blur((g - blur(g, 3)) ** 2, 4)) / c['line_contrast_scale'])
    face = face_mask(a, subject); ld = blur((l1 > .5).astype(np.float32), 6)
    busy = (ld > c['texture_density_max']) & (face < .3)
    bold = unit(blur(cv2.dilate(l2 * contrast, np.ones((3, 3), np.uint8)), .8) * 1.3)  # thick main strokes
    bd = blur((l2 > .5).astype(np.float32), 8); busy2 = unit((bd - .18) / .12) * (1 - face)
    bold = bold * (1 - .6 * busy2)  # busy foliage/snow: fewer leopard-spot strokes
    wash = unit(np.maximum(wash, blur(busy2, 4) * .30))  # ... plus a soft mid-ink mass (写意 tree mass)
    fine = l1 * np.where(busy, 0., c['fine_line_weight'] + .55 * face)  # no fine etching in busy texture
    line = unit(np.maximum(bold, fine))
    hf = blur(g, .7) - blur(g, 1.6); breaks = unit(.5 + lnorm(hf, 3) * .8)  # input-derived dry-brush gaps
    line = line * (1 - c['dry_break'] * (1 - breaks))
    line = unit(np.maximum(line, blur(line, c['line_bleed'] * 2) * .55))  # ink bleeding halo
    tx, ty, coh, en = tensor(g, 4); tex = unit(var / .02) * (1 - face) * (1 - blank)
    cun = lic(lnorm(hf, 3), tx, ty, c['cun_len']); cun = unit(-cun) * tex * c['cun_strength']
    wash = wash * (1 - face * (1 - c['face_wash']))
    D = unit(1 - (1 - wash) * (1 - line) * (1 - cun))
    paper = np.array(c['paper_rgb'], np.float32); inkc = np.array(c['ink_rgb'], np.float32)
    rgb = paper * (1 - D[..., None]) + inkc * D[..., None]
    rgb = rgb + (lnorm(g - blur(g, 1.0), 3) * c['paper_grain'])[..., None] * (1 - D[..., None])
    return unit(rgb), {'far_fade': 'local sharpness proxy (depth would need global context)'}


def hue_pull(h, anchors, k, sigma=28.):
    # SMOOTH pull (v6_03): soft-weighted anchor offsets; nearest-anchor argmin split mid-hues into two colours
    a = np.array(anchors, np.float32)[None, None]; dd = ((a - h[..., None] + 180) % 360) - 180
    w = np.exp(-(dd / sigma) ** 2); off = (w * dd).sum(-1) / (w.sum(-1) + 1e-3)
    return (h + k * off) % 360


def vangogh(a, subject, A):
    c = P['vangogh']; g = gray(a); face = face_mask(a, subject)
    tx, ty, coh, en = tensor(g, c['tensor_sigma'])
    base = kuwahara(a, tx, ty, c['kuwahara_radius'])
    hsv = cv2.cvtColor(unit(base), cv2.COLOR_RGB2HSV); H, S, V = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    k = c['hue_pull'] * (1 - .5 * face); H = hue_pull(H, c['hue_anchors'], k)
    tgt = np.where(V < .45, c['shadow_hue'], c['highlight_hue']).astype(np.float32)  # cool shadows, warm lights
    lowsat = unit((c['min_sat'] - S) / c['min_sat']) * (1 - face)
    # chromatic pixels: gentle pull; near-grey pixels: hue SET to target (unstable hue caused pink fringes)
    dd = ((tgt - H + 180) % 360) - 180; H = (H + dd * c['tone_pull'] * lowsat) % 360  # only greyish pixels
    H = np.where(lowsat > .5, tgt, H).astype(np.float32)
    S = unit(np.maximum(S * (c['sat_gain'] - .4 * face), np.minimum(c['grey_tint_sat'], c['min_sat'] * .8) * (1 - face)))
    base = cv2.cvtColor(np.stack([H, S, V], -1).astype(np.float32), cv2.COLOR_HSV2RGB)
    detail = unit(np.sqrt(blur((g - blur(g, 1.5)) ** 2, 4)) / c['detail_scale'])
    bp = blur(g, c['noise_blur']) - blur(g, 3.5)
    gate = unit(np.sqrt(blur(bp * bp, 5)) / c['amp_floor'])  # no amplification of flat/dark regions
    noise = lnorm(bp, 5) * gate
    ts, tl = lic(noise, tx, ty, c['lic_short']), lic(noise, tx, ty, c['lic_long'])
    height = lnorm(ts * detail + tl * (1 - detail), 6)
    amp = c['stroke_amp'] * (1 - face * (1 - c['face_scale']))
    y = base * (1 + (height * amp)[..., None])
    hs = cv2.cvtColor(unit(y), cv2.COLOR_RGB2HSV); hs[..., 1] = unit(hs[..., 1] * (1 + c['stroke_sat'] * height))
    y = cv2.cvtColor(hs, cv2.COLOR_HSV2RGB)
    dx = cv2.Sobel(height, cv2.CV_32F, 1, 0) / 8; dy = cv2.Sobel(height, cv2.CV_32F, 0, 1) / 8
    y = y + (np.tanh((-dx - dy) * 3) * c['emboss'] * (1 - .5 * face))[..., None]
    ol = xdog(g, 1.4, eps=.015) * unit((coh - .4) / .3) * c['outline_alpha']
    y = y * (1 - ol[..., None]) + np.array(c['outline_rgb'], np.float32) * ol[..., None]
    return unit(y), {'LIC': [c['lic_short'], c['lic_long']], 'palette_remap': True}


FN = {'vangogh': vangogh, 'ukiyoe': ukiyoe, 'ink': ink}


def render(a, subject, style, A):
    rows = np.flatnonzero(a.mean((1, 2)) > .008)  # keep exact-black letterbox rows unchanged
    top, bot = (int(rows[0]), int(rows[-1]) + 1) if len(rows) else (0, a.shape[0])
    y = a.copy(); y[top:bot] = FN[style](a[top:bot], subject[top:bot], A)[0]; return y


def load(p, m=None):
    a = np.asarray(Image.open(p).convert('RGB'), np.float32) / 255
    s = np.asarray(Image.open(m).convert('L'), np.float32) / 255 if m and Path(m).exists() else np.zeros(a.shape[:2], np.float32)
    return a, s
def allowed(split):
    ok = {Path(p.replace('\\', '/')).stem for p in json.loads((V3 / 'data/splits.json').read_text())[split]}
    return [p for p in sorted((V3 / 'data/claude_targets/content' / split).glob('*.png')) if p.stem in ok]


def mask_for(p, split): return V3 / 'data/claude_targets/content_masks' / split / p.name


def preview_rows(out):
    files = sorted((V3 / 'data/claude_targets/content/validation').glob('*.png'))
    rows = [('validation_' + files[i].stem, files[i], mask_for(files[i], 'validation'))
            for i in np.linspace(0, len(files) - 1, 12).round().astype(int)]
    pairs = sorted((V3 / 'data/video/train_pairs').glob('*.npz'))
    for i, p in enumerate([pairs[j] for j in np.linspace(0, len(pairs) - 1, 3).round().astype(int)]):
        assert max(int(v) for v in re.findall(r'\d+', p.stem)) <= 624, p
        src = out / f'sintel_training_{i}.png'; Image.fromarray(np.load(p)['a']).save(src); rows.append(('sintel_training_' + str(i), src, None))
    return rows


def locality(out, rows, A):
    res = []
    for idx in (0, 2, 3):
        name, p, m = rows[idx]; a, s = load(p, m); h, w = a.shape[:2]; t0, l0 = (h - 256) // 2, (w - 256) // 2
        for st in STYLES:
            full = np.asarray(Image.open(out / 'native' / f'{name}_{st}.png'), np.float32)[t0:t0 + 256, l0:l0 + 256] / 255
            loc = render(a[t0:t0 + 256, l0:l0 + 256], s[t0:t0 + 256, l0:l0 + 256], st, A)
            res.append({'scene': name, 'style': st, 'central192_MAE': float(np.abs(full - loc)[32:-32, 32:-32].mean())})
    summ = {st: float(np.mean([r['central192_MAE'] for r in res if r['style'] == st])) for st in STYLES}
    return {'rows': res, 'mean_by_style': summ, 'threshold': .01, 'pass': all(v <= .01 for v in summ.values())}


def preview(out):
    out.mkdir(parents=True, exist_ok=False); (out / 'native').mkdir(); A = build_assets()
    (out / 'teacher_assets.json').write_text(json.dumps(A, indent=2)); (out / 'params.json').write_text(json.dumps(P, indent=2))
    (out / 'source_claude_targets_v6.py').write_bytes(Path(__file__).read_bytes())
    rows = preview_rows(out); t0 = time.time(); timing = []
    for off in range(0, len(rows), 3):
        sub = rows[off:off + 3]; sheet = Image.new('RGB', (4 * 320, len(sub) * 262), 'white'); dr = ImageDraw.Draw(sheet)
        for ri, (name, p, m) in enumerate(sub):
            a, s = load(p, m); ims = [a]
            for st in STYLES:
                t1 = time.time(); y = render(a, s, st, A); timing.append(time.time() - t1)
                Image.fromarray((y * 255).round().astype(np.uint8)).save(out / 'native' / f'{name}_{st}.png'); ims.append(y)
            for col, (lab, v) in enumerate(zip(('INPUT', 'VANGOGH TEACHER', 'UKIYOE TEACHER', 'INK TEACHER'), ims)):
                im = Image.fromarray((unit(v) * 255).round().astype(np.uint8)); im.thumbnail((320, 240)); sheet.paste(im, (col * 320, ri * 262))
                dr.text((col * 320 + 2, ri * 262 + 243), name + ' ' + lab, fill='black')
        sheet.save(out / f'contact_{off // 3 + 1}.jpg', quality=92)
    loc = locality(out, rows, A)
    meta = {'version': P['version'], 'generator_sha256': sha(__file__), 'params_sha256': sha(out / 'params.json'),
            'assets_sha256': sha(out / 'teacher_assets.json'), 'seconds_per_style_image_mean': float(np.mean(timing)),
            'fixed17_used': False, 'heldout_video_used': False, 'all_images_are_teacher': True, 'locality': loc,
            'rows': [{'name': n, 'input': str(p), 'input_sha256': sha(p)} for n, p, _ in rows]}
    (out / 'preview_manifest.json').write_text(json.dumps(meta, indent=2)); print(json.dumps({k: meta[k] for k in ('seconds_per_style_image_mean', 'locality')}, indent=1))


def generate(root, style, A, limits=None):
    """Write targets for one style; resumable (skips existing files whose hash is already recorded)."""
    root.mkdir(parents=True, exist_ok=True); part = root / f'_partial_{style}.jsonl'; done = {}
    if part.exists():
        for line in part.read_text().splitlines():
            r = json.loads(line); done[(r['split'], r['stem'])] = r
    with part.open('a') as f:
        for split in ('train', 'validation'):
            files = allowed(split)
            if limits: files = [files[i] for i in np.linspace(0, len(files) - 1, min(limits[split], len(files))).round().astype(int)]
            d = root / style / split; d.mkdir(parents=True, exist_ok=True)
            for p in files:
                o = d / p.name
                if (split, p.stem) in done and o.exists() and sha(o) == done[(split, p.stem)]['target_sha256']: continue
                a, s = load(p, mask_for(p, split)); y = render(a, s, style, A)
                Image.fromarray((y * 255).round().astype(np.uint8)).save(o)
                r = {'split': split, 'stem': p.stem, 'input': str(p), 'input_sha256': sha(p), 'target': str(o), 'target_sha256': sha(o)}
                f.write(json.dumps(r) + '\n'); f.flush()
    return part


def finalize(root, gate_path):
    gate = json.loads(gate_path.read_text()); rows = []
    for st in STYLES:
        rr = {}
        for line in (root / f'_partial_{st}.jsonl').read_text().splitlines():
            r = json.loads(line); rr[(r['split'], r['stem'])] = r
        assert len(rr) == 1263, (st, len(rr)); rows += [{'style': st, **v} for v in rr.values()]
    (root / 'manifest.json').write_text(json.dumps({'rows': rows}, indent=1))
    (root / 'config.json').write_text(json.dumps({'gate_sha256': sha(gate_path), 'teachers': gate['teachers'], 'params': P,
                                                  'generator_sha256': sha(__file__), 'fixed17_used': False}, indent=2))
    (root / 'finished.json').write_text(json.dumps({'count': 1263, 'target_images': len(rows), 'manifest_sha256': sha(root / 'manifest.json'),
                                                    'time': time.strftime('%Y-%m-%dT%H:%M:%S+08:00')}, indent=2))


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--preview'); ap.add_argument('--style'); ap.add_argument('--root')
    ap.add_argument('--calib', action='store_true'); ap.add_argument('--finalize', action='store_true'); ap.add_argument('--gate')
    a = ap.parse_args(); cv2.setNumThreads(2)
    if a.preview: preview(ROOT / a.preview)
    elif a.finalize: finalize(ROOT / a.root, ROOT / a.gate)
    else:
        if not a.calib:  # formal P2 must use the generator version locked in G1_APPROVAL.json
            g = json.loads((ROOT / a.gate).read_text()); assert g['teachers']['generator_sha256'] == sha(__file__), 'generator changed since G1 lock'
        generate(ROOT / a.root, a.style, build_assets(), {'train': 64, 'validation': 12} if a.calib else None)
