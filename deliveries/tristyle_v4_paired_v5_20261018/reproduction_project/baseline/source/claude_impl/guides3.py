"""v3 targets: content-PREDICTABLE strokes (diagnosis 2026-10-17 00:55).

Student v3a/v3b VG produced a stationary diamond lattice: AdaIN stroke placement is not a function of
the content the student sees, so L1/high-pass regression averages it out and texture statistics reward
any periodic texture.  Here every mark is a deterministic local function of the input:
  phase bands  = sin(2*pi*f*u), u = smoothed luminance + amplified local contrast (isophotes follow form,
                 long sweeping in smooth sky, short and dense in textured vegetation -> multi-scale)
  flow         = structure-tensor tangent field (edge-following; large-scale smoothing in flat regions)
  brush        = line-integral convolution of the bands along the flow (curved, connected strokes)
Colour layering: light strokes warmer, dark strokes cooler; palette from the low-passed AdaIN VG target.
"""
import numpy as np, cv2
from guides import xdog, _lab
from guides2 import _keep_long

def flow_field(gray, s_grad=1.5, s_tensor=6.0, s_coarse=24.0):
    g = cv2.GaussianBlur(gray, (0, 0), s_grad)
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3); gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
    def tens(s):
        return [cv2.GaussianBlur(a, (0, 0), s) for a in (gx * gx, gy * gy, gx * gy)]
    exx, eyy, exy = tens(s_tensor); cxx, cyy, cxy = tens(s_coarse)
    mag = np.sqrt((exx - eyy) ** 2 + 4 * exy ** 2); cmag = np.sqrt((cxx - cyy) ** 2 + 4 * cxy ** 2)
    w = np.clip(mag / (mag + cmag * 0.5 + 1e-6), 0, 1)  # local coherent structure vs coarse context
    a = (1 - w) * cxx + w * exx; b = (1 - w) * cyy + w * eyy; c = (1 - w) * cxy + w * exy
    theta = 0.5 * np.arctan2(2 * c, a - b)  # dominant gradient orientation
    tx, ty = -np.sin(theta), np.cos(theta)    # tangent (perpendicular to gradient)
    return tx.astype(np.float32), ty.astype(np.float32)

def lic(field, tx, ty, length=10, step=1.0):
    h, w = field.shape; gy, gx = np.mgrid[:h, :w].astype(np.float32); acc = field.copy(); wsum = np.ones_like(field)
    for sgn in (1, -1):
        x, y = gx.copy(), gy.copy(); dx, dy = tx * sgn, ty * sgn
        for i in range(length):
            x = x + dx * step; y = y + dy * step
            ndx = cv2.remap(tx, x, y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT); ndy = cv2.remap(ty, x, y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
            flip = np.sign(ndx * dx + ndy * dy + 1e-6); dx, dy = ndx * flip, ndy * flip  # keep direction consistent
            wt = 1 - i / length
            acc += wt * cv2.remap(field, x, y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT); wsum += wt
    return acc / wsum

def vangogh3(rgb, vg_adain):
    """rgb, vg_adain: uint8 HxWx3 (content photo, AdaIN VG target of the same photo)."""
    h, w = rgb.shape[:2]
    g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255
    gb = cv2.bilateralFilter(g, 7, 0.1, 5)
    u = gb + 1.6 * (gb - cv2.GaussianBlur(gb, (0, 0), 12))
    tx, ty = flow_field(gb)
    b1 = 0.5 + 0.5 * np.sin(2 * np.pi * 9.0 * u)          # broad strokes
    b2 = 0.5 + 0.5 * np.sin(2 * np.pi * 23.0 * u + 1.3)   # fine bristle strokes
    s1 = lic(b1, tx, ty, 12); s2 = lic(b2, tx, ty, 6)
    stroke = 0.6 * s1 + 0.4 * s2
    stroke = np.clip((stroke - stroke.mean()) / (stroke.std() + 1e-6), -2, 2) / 2  # [-1,1]
    # palette: low-passed AdaIN VG colour (keeps VG hues/layering), with content chroma for semantics
    lab_v = _lab(cv2.GaussianBlur(vg_adain, (0, 0), 3)); lab_c = _lab(cv2.bilateralFilter(rgb, 9, 30, 7))
    L = 0.55 * lab_v[..., 0] + 0.45 * lab_c[..., 0]
    A = 0.5 * lab_v[..., 1] + 0.5 * (128 + (lab_c[..., 1] - 128) * 1.4)
    B = 0.5 * lab_v[..., 2] + 0.5 * (128 + (lab_c[..., 2] - 128) * 1.4)
    L = L + 22 * stroke                       # impasto light/dark
    B = B + 10 * stroke                       # warm light strokes / cool dark strokes
    A = A - 3 * stroke
    # dark blue-black contours along strong, long edges (VG outlines forms)
    e = _keep_long(xdog(gb, sigma=1.4, p=22, eps=0.012, phi=9) < 0.5, max(30, h * w // 7000)).astype(np.float32)
    e = lic(cv2.GaussianBlur(e, (0, 0), 0.8), tx, ty, 4)
    L = L * (1 - 0.55 * e); A = A * (1 - 0.3 * e) + 128 * 0.3 * e; B = B * (1 - 0.4 * e) + 100 * 0.4 * e
    out = cv2.cvtColor(np.clip(np.stack([L, A, B], -1), 0, 255).astype(np.uint8), cv2.COLOR_LAB2RGB)
    return out.astype(np.float32) / 255

def ink3(rgb):
    """Ink with deterministic, form-following brush structure (no random fields)."""
    h, w = rgb.shape[:2]
    g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255
    gs = cv2.bilateralFilter(g, 9, 0.12, 6); mu = cv2.GaussianBlur(gs, (0, 0), 25)
    tx, ty = flow_field(gs)
    dens = np.clip(0.8 * (1 - gs) ** 1.4 + 0.9 * (mu - gs), 0, 1)
    # wash: soft, LIC-smeared along form so it reads as brushed wash, with bleed rim on wet accents
    wet = lic(cv2.GaussianBlur(dens, (0, 0), 2.0), tx, ty, 8)
    wash = 0.20 * (0.5 + 0.5 * np.tanh((wet - 0.15) * 8)) + 0.25 * (0.5 + 0.5 * np.tanh((wet - 0.38) * 8)) + 0.15 * (0.5 + 0.5 * np.tanh((wet - 0.55) * 8))
    acc = 0.5 + 0.5 * np.tanh((cv2.GaussianBlur(dens, (0, 0), 4) - 0.78) * 12)
    wetink = np.maximum(acc * 0.5, cv2.GaussianBlur(acc, (0, 0), 3.5) * 0.3)
    # dry brush: long contours, broken by deterministic bristle bands (phase of local luminance) along flow
    u = gs + 1.5 * (gs - cv2.GaussianBlur(gs, (0, 0), 10))
    bristle = lic(0.5 + 0.5 * np.sin(2 * np.pi * 26 * u), tx, ty, 6)
    e = _keep_long((1 - xdog(gs, sigma=1.4, p=22, eps=0.01, phi=10)) > 0.5, max(25, h * w // 9000)).astype(np.float32)
    e = lic(cv2.dilate(e, np.ones((2, 2), np.uint8)), tx, ty, 3)
    dry = np.clip(e * 1.6, 0, 1) * np.clip(0.35 + 1.1 * bristle, 0, 1)
    # texture strokes (cun) in textured, darker-than-surround zones: flow-aligned bands, not random dots
    det = np.abs(gs - cv2.GaussianBlur(gs, (0, 0), 2)); texm = np.clip((cv2.GaussianBlur(det, (0, 0), 8) - 0.015) * 25, 0, 1)
    cun = texm * (gs < mu + 0.03) * np.clip((lic(0.5 + 0.5 * np.sin(2 * np.pi * 14 * u), tx, ty, 5) - 0.55) * 3, 0, 1)
    yy = np.linspace(0, 1, h, dtype=np.float32)[:, None]
    mist = np.clip(1 - (yy - 0.12) / 0.5, 0, 1) * 0.5 * (1 - 0.6 * texm) * (0.8 + 0.2 * np.clip((cv2.GaussianBlur(gs, (0, 0), 30) - 0.5) * 3, -1, 1))
    neg = np.clip((gs - 0.70) * 3.0, 0, 1) * (1 - texm)
    total = np.clip(0.85 * wash + wetink + 0.95 * dry + 0.55 * cun, 0, 1) * (1 - mist) * (1 - 0.85 * neg)
    paper = np.array([0.95, 0.93, 0.87], np.float32)[None, None]
    col = cv2.GaussianBlur(rgb.astype(np.float32) / 255, (0, 0), 5); tint = paper * (1 + 0.12 * (col - col.mean(2, keepdims=True)))
    return np.clip(tint * (1 - total[..., None]) + np.float32(0.08) * total[..., None], 0, 1)

def vangogh4(rgb, vg_adain):
    """VG3 + stronger impasto, structure-preserving: flow smoothing restricted (s_coarse 12) so
    windows/towers keep straight edges; stroke amplitude higher in smooth areas, lower on fine detail."""
    h, w = rgb.shape[:2]
    g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255
    gb = cv2.bilateralFilter(g, 7, 0.1, 5)
    u = gb + 1.6 * (gb - cv2.GaussianBlur(gb, (0, 0), 12))
    tx, ty = flow_field(gb, s_tensor=4.0, s_coarse=12.0)
    s1 = lic(0.5 + 0.5 * np.sin(2 * np.pi * 8.0 * u), tx, ty, 14); s2 = lic(0.5 + 0.5 * np.sin(2 * np.pi * 21.0 * u + 1.3), tx, ty, 7)
    stroke = 0.6 * s1 + 0.4 * s2; stroke = np.clip((stroke - stroke.mean()) / (stroke.std() + 1e-6), -2, 2) / 2
    det = np.abs(gb - cv2.GaussianBlur(gb, (0, 0), 1.5)); detail = np.clip(cv2.GaussianBlur(det, (0, 0), 3) * 30, 0, 1)
    amp = 30 * (1 - 0.6 * detail)
    lab_v = _lab(cv2.GaussianBlur(vg_adain, (0, 0), 3)); lab_c = _lab(cv2.bilateralFilter(rgb, 9, 30, 7))
    L = 0.5 * lab_v[..., 0] + 0.5 * lab_c[..., 0] + amp * stroke
    A = 0.5 * lab_v[..., 1] + 0.5 * (128 + (lab_c[..., 1] - 128) * 1.5) - 4 * stroke
    B = 0.5 * lab_v[..., 2] + 0.5 * (128 + (lab_c[..., 2] - 128) * 1.5) + 14 * stroke
    e = _keep_long(xdog(gb, sigma=1.2, p=22, eps=0.012, phi=9) < 0.5, max(30, h * w // 7000)).astype(np.float32)
    e = cv2.GaussianBlur(e, (0, 0), 0.7)
    L = L * (1 - 0.5 * e); A = A * (1 - 0.3 * e) + 128 * 0.3 * e; B = B * (1 - 0.4 * e) + 100 * 0.4 * e
    return cv2.cvtColor(np.clip(np.stack([L, A, B], -1), 0, 255).astype(np.uint8), cv2.COLOR_LAB2RGB).astype(np.float32) / 255

def ink4(rgb):
    """Ink3 with graded (not threshold-like) density: wet accents only in the darkest large masses,
    lighter graded washes, thinner dry contours, faces/fine detail preserved by detail-aware density cap."""
    h, w = rgb.shape[:2]
    g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255
    gs = cv2.bilateralFilter(g, 9, 0.12, 6); mu = cv2.GaussianBlur(gs, (0, 0), 25)
    tx, ty = flow_field(gs, s_tensor=4.0, s_coarse=14.0)
    dens = np.clip(0.75 * (1 - gs) ** 1.2 + 0.6 * (mu - gs), 0, 1)
    wet = lic(cv2.GaussianBlur(dens, (0, 0), 1.5), tx, ty, 6)
    wash = sum(a * (0.5 + 0.5 * np.tanh((wet - t) * 6)) for a, t in ((0.16, 0.12), (0.18, 0.30), (0.18, 0.48), (0.14, 0.66)))
    big = cv2.GaussianBlur(dens, (0, 0), 6)
    acc = 0.5 + 0.5 * np.tanh((big - 0.80) * 10); wetink = np.maximum(acc * 0.35, cv2.GaussianBlur(acc, (0, 0), 4) * 0.25)
    u = gs + 1.5 * (gs - cv2.GaussianBlur(gs, (0, 0), 10))
    bristle = lic(0.5 + 0.5 * np.sin(2 * np.pi * 26 * u), tx, ty, 6)
    e = _keep_long((1 - xdog(gs, sigma=1.1, p=22, eps=0.01, phi=10)) > 0.5, max(25, h * w // 9000)).astype(np.float32)
    e = lic(e, tx, ty, 3)
    dry = np.clip(e * 1.4, 0, 1) * np.clip(0.4 + 1.0 * bristle, 0, 1)
    det = np.abs(gs - cv2.GaussianBlur(gs, (0, 0), 2)); texm = np.clip((cv2.GaussianBlur(det, (0, 0), 8) - 0.015) * 25, 0, 1)
    cun = texm * (gs < mu + 0.03) * np.clip((lic(0.5 + 0.5 * np.sin(2 * np.pi * 14 * u), tx, ty, 5) - 0.55) * 3, 0, 1)
    yy = np.linspace(0, 1, h, dtype=np.float32)[:, None]
    mist = np.clip(1 - (yy - 0.12) / 0.5, 0, 1) * 0.45 * (1 - 0.6 * texm)
    neg = np.clip((gs - 0.72) * 3.0, 0, 1) * (1 - texm)
    total = np.clip(wash + wetink + 0.85 * dry + 0.5 * cun, 0, 0.92) * (1 - mist) * (1 - 0.85 * neg)
    paper = np.array([0.95, 0.93, 0.87], np.float32)[None, None]
    col = cv2.GaussianBlur(rgb.astype(np.float32) / 255, (0, 0), 5); tint = paper * (1 + 0.12 * (col - col.mean(2, keepdims=True)))
    return np.clip(tint * (1 - total[..., None]) + np.float32(0.08) * total[..., None], 0, 1)

def vangogh5(rgb, vg_adain):
    """Painterly abstraction first (removes photographic micro-detail/shading), then flow strokes everywhere.
    Base colour: mean-shift + bilateral abstraction of the photo, chroma boosted toward VG's saturated palette,
    mixed with low-passed AdaIN colour. Strokes: two scales; in detailed regions shorter LIC (dabs) instead of
    weaker amplitude, so busy scenes (faces, interiors) also become painted."""
    h, w = rgb.shape[:2]
    ab = cv2.pyrMeanShiftFiltering(rgb, 8, 24, maxLevel=1)
    for _ in range(2): ab = cv2.bilateralFilter(ab, 9, 40, 7)
    g = cv2.cvtColor(ab, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255
    g0 = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255
    u = g + 1.4 * (g - cv2.GaussianBlur(g, (0, 0), 10))
    tx, ty = flow_field(cv2.GaussianBlur(g0, (0, 0), 1.0), s_tensor=4.0, s_coarse=12.0)
    det = np.abs(g0 - cv2.GaussianBlur(g0, (0, 0), 1.5)); detail = np.clip(cv2.GaussianBlur(det, (0, 0), 3) * 30, 0, 1)[..., None]
    sA = lic(0.5 + 0.5 * np.sin(2 * np.pi * 8.0 * u), tx, ty, 14); sB = lic(0.5 + 0.5 * np.sin(2 * np.pi * 21.0 * u + 1.3), tx, ty, 7)
    sC = lic(0.5 + 0.5 * np.sin(2 * np.pi * 30.0 * u + 0.4), tx, ty, 4)  # short dabs for detailed zones
    d = detail[..., 0]
    stroke = (1 - d) * (0.6 * sA + 0.4 * sB) + d * (0.5 * sB + 0.5 * sC)
    stroke = np.clip((stroke - stroke.mean()) / (stroke.std() + 1e-6), -2, 2) / 2
    lab_v = _lab(cv2.GaussianBlur(vg_adain, (0, 0), 4)); lab_a = _lab(ab)
    L = 0.35 * lab_v[..., 0] + 0.65 * lab_a[..., 0] + 26 * stroke
    A = 0.35 * lab_v[..., 1] + 0.65 * (128 + (lab_a[..., 1] - 128) * 1.6) - 4 * stroke
    B = 0.35 * lab_v[..., 2] + 0.65 * (128 + (lab_a[..., 2] - 128) * 1.6) + 14 * stroke
    e = _keep_long(xdog(g, sigma=1.2, p=22, eps=0.012, phi=9) < 0.5, max(30, h * w // 7000)).astype(np.float32)
    e = cv2.GaussianBlur(e, (0, 0), 0.8)
    L = L * (1 - 0.5 * e); A = A * (1 - 0.3 * e) + 128 * 0.3 * e; B = B * (1 - 0.4 * e) + 100 * 0.4 * e
    return cv2.cvtColor(np.clip(np.stack([L, A, B], -1), 0, 255).astype(np.uint8), cv2.COLOR_LAB2RGB).astype(np.float32) / 255
