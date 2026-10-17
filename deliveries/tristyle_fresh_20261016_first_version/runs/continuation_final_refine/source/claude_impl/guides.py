"""Claude v3 per-style paired training targets (deterministic, per image).

Van Gogh: AdaIN (official MIT pytorch-AdaIN weights) with statistics interpolated between
two coherent public-domain anchors, then partial chroma retention so semantics survive.
Ukiyo-e / ink: form-aware non-photorealistic rendering written here (no external network).
Targets are artistic *guidance*; the student is trained on them plus perceptual/temporal terms.
"""
import sys, pathlib, hashlib
import numpy as np, cv2, torch
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def seed_of(key):
    return int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)

def smooth_noise(h, w, scale, rng, aniso=None):
    n = rng.standard_normal((h // scale + 3, w // scale + 3)).astype(np.float32)
    n = cv2.resize(n, (w + 3 * scale, h + 3 * scale), interpolation=cv2.INTER_CUBIC)[:h, :w]
    return n / (n.std() + 1e-6)

def xdog(gray, sigma=1.0, k=1.6, p=20.0, eps=0.02, phi=12.0):
    g1 = cv2.GaussianBlur(gray, (0, 0), sigma); g2 = cv2.GaussianBlur(gray, (0, 0), sigma * k)
    d = (1 + p) * g1 - p * g2
    e = np.where(d >= eps, 1.0, 1.0 + np.tanh(phi * (d - eps)))
    return np.clip(e, 0, 1).astype(np.float32)  # 1 = paper, 0 = line

# ---------------------------------------------------------------- ukiyo-e
UKIYOE_PALETTE = np.array([  # sampled-by-eye traditional print colors (RGB)
    [33, 52, 86],    # indigo / prussian blue (dark)
    [53, 92, 135],   # prussian blue
    [118, 160, 180], # light blue
    [196, 214, 208], # pale aqua
    [236, 224, 196], # paper beige
    [222, 196, 150], # ochre light
    [196, 150, 92],  # ochre
    [178, 82, 58],   # vermilion/red-brown
    [214, 128, 108], # pink-red
    [92, 120, 78],   # muted green
    [150, 168, 108], # light green
    [70, 58, 48],    # dark brown
    [28, 26, 30],    # sumi black
], np.float32)

def _lab(rgb_u8):
    return cv2.cvtColor(rgb_u8, cv2.COLOR_RGB2LAB).astype(np.float32)

PAL_LAB = _lab(UKIYOE_PALETTE.astype(np.uint8)[None])[0]

def ukiyoe(rgb, key='x'):
    rng = np.random.default_rng(seed_of('u' + key)); h, w = rgb.shape[:2]
    small = cv2.pyrMeanShiftFiltering(rgb, 10, 28, maxLevel=1)
    for _ in range(2): small = cv2.bilateralFilter(small, 9, 40, 7)
    lab = _lab(small).reshape(-1, 3)
    K = 9
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    cv2.setRNGSeed(seed_of('k' + key) % 2**31)
    _, lbl, cent = cv2.kmeans(lab[::7].copy(), K, None, crit, 2, cv2.KMEANS_PP_CENTERS)
    d = ((lab[:, None, :] - cent[None]) ** 2).sum(-1); lbl = d.argmin(1).reshape(h, w).astype(np.uint8)
    lbl = cv2.medianBlur(lbl, 7)
    # map each cluster centre to the palette: chroma-aware, luminance stretched
    out_c = []
    for c in cent:
        dd = (((PAL_LAB[:, 1:] - c[1:]) ** 2).sum(-1) + 0.15 * (PAL_LAB[:, 0] - c[0]) ** 2)
        if np.hypot(c[1] - 128, c[2] - 128) < 14:  # neutral: blue family only if bluish, else warm paper/brown
            fam = [0, 1, 2, 3] if c[2] < 127 else [4, 5, 11, 12]
            dd = dd + 1e6 * ~np.isin(np.arange(len(PAL_LAB)), fam)
        j = dd.argmin(); chroma = np.hypot(c[1] - 128, c[2] - 128)
        wpal = 0.6 if chroma < 14 else 0.3  # keep strongly coloured hues (skin, flags) recognisable
        m = c.copy(); m[1:] = wpal * PAL_LAB[j, 1:] + (1 - wpal) * (128 + (c[1:] - 128) * 1.2)
        m[0] = 50 + 0.78 * c[0]  # lighter print values, lifted shadows
        out_c.append(m)
    out_c = np.array(out_c, np.float32)
    flat = out_c[lbl]
    flat = cv2.cvtColor(np.clip(flat, 0, 255).astype(np.uint8), cv2.COLOR_LAB2RGB).astype(np.float32) / 255
    # bokashi gradient in sky-like regions (bright, smooth, touching top)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255
    tex = cv2.GaussianBlur(np.abs(cv2.Laplacian(cv2.GaussianBlur(gray, (0, 0), 1.5), cv2.CV_32F)), (0, 0), 6)
    top = set(np.unique(lbl[: max(2, h // 20)]).tolist())
    yy = np.linspace(0, 1, h, dtype=np.float32)[:, None]
    sky = np.isin(lbl, list(top)) & (tex < 0.012) & (yy < 0.6)
    sky = cv2.GaussianBlur(sky.astype(np.float32), (0, 0), 3)[..., None]
    grad = np.clip(1 - yy / 0.45, 0, 1)[..., None] ** 1.5
    blue = UKIYOE_PALETTE[1] / 255
    flat = flat * (1 - sky * grad * 0.75) + blue * sky * grad * 0.75
    # contours: fluent dark lines on structure edges only
    sg = cv2.cvtColor((small).astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32) / 255
    e = xdog(sg, sigma=1.1, p=24, eps=0.015, phi=8)
    b = (cv2.morphologyEx(lbl, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)) > 0).astype(np.float32)
    line = np.minimum(e, 1 - 0.55 * cv2.GaussianBlur(b, (0, 0), 0.7))
    line = cv2.GaussianBlur(line, (0, 0), 0.6)[..., None]
    ink = np.array([30, 32, 44], np.float32) / 255
    out = flat * line + ink * (1 - line)
    # restrained wood-grain/paper texture
    grain = smooth_noise(h, w, 2, rng) * 0.012 + cv2.GaussianBlur(rng.standard_normal((h, w)).astype(np.float32), (0, 0), 0.7) * 0.012
    out = out + grain[..., None]
    paper = np.array([0.95, 0.91, 0.82], np.float32)
    out = out * (0.92 + 0.08 * paper)
    return np.clip(out, 0, 1)

# ---------------------------------------------------------------- ink
def ink(rgb, key='x'):
    rng = np.random.default_rng(seed_of('i' + key)); h, w = rgb.shape[:2]
    g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255
    gs = cv2.bilateralFilter(g, 9, 0.12, 6)
    # local contrast normalisation -> organized ink density (dark = 1)
    mu = cv2.GaussianBlur(gs, (0, 0), 25)
    dens = np.clip(1 - gs, 0, 1)
    dens = np.clip(0.75 * dens ** 1.3 + 0.9 * (mu - gs), 0, 1)
    # wash: three soft ink levels with bleeding irregular borders
    n1 = smooth_noise(h, w, 6, rng); n2 = smooth_noise(h, w, 24, rng)
    wet = cv2.GaussianBlur(dens, (0, 0), 3.0) + 0.025 * n1 + 0.02 * n2
    levels = np.array([0.0, 0.22, 0.48, 0.85], np.float32)
    q = np.zeros_like(wet)
    for a, b in zip(levels[:-1], levels[1:]):
        t = (a + b) / 2
        q += (b - a) * (0.5 + 0.5 * np.tanh((wet - t) * 18))
    wash = cv2.GaussianBlur(q, (0, 0), 1.8)
    # bleed halo: diffused darker rim at wash borders
    rim = np.clip(cv2.GaussianBlur(q, (0, 0), 5) - q, 0, 1)
    wash = wash + 0.25 * rim
    # dry brush contour strokes, broken by streaky noise
    e = 1 - xdog(gs, sigma=1.3, p=22, eps=0.01, phi=10)
    streak = cv2.blur(rng.random((h, w)).astype(np.float32), (9, 1))
    streak2 = cv2.blur(rng.random((h, w)).astype(np.float32), (1, 9))
    gy = cv2.Sobel(gs, cv2.CV_32F, 0, 1, ksize=5); gx = cv2.Sobel(gs, cv2.CV_32F, 1, 0, ksize=5)
    horiz = (np.abs(gy) > np.abs(gx)).astype(np.float32)  # edge runs horizontally
    st = horiz * streak + (1 - horiz) * streak2
    dry = e * np.clip((st - 0.38) * 5, 0, 1)
    dry = np.maximum(dry, cv2.GaussianBlur(e, (0, 0), 1.5) * 0.35)
    # texture strokes (cun / dots) where content is textured
    det = np.abs(gs - cv2.GaussianBlur(gs, (0, 0), 2))
    tex = cv2.GaussianBlur(det, (0, 0), 8)
    texm = np.clip((tex - 0.015) * 25, 0, 1)
    dots = (rng.random((h, w)) < 0.05).astype(np.float32)
    dots = cv2.dilate(dots, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    dots = cv2.GaussianBlur(dots, (0, 0), 0.8) * (det > 0.03)
    cun = texm * np.clip(0.6 * dots + 1.3 * det * (gs < mu), 0, 1)
    # mist / atmospheric depth: fade far (upper) and bright smooth areas toward paper
    yy = np.linspace(0, 1, h, dtype=np.float32)[:, None]
    mist = np.clip(1 - (yy - 0.15) / 0.55, 0, 1) * 0.45 * (1 - texm * 0.5)
    mist = mist * (0.7 + 0.3 * n2.clip(-1, 1))
    bright_smooth = np.clip((gs - 0.65) * 3, 0, 1) * (1 - texm)
    total = np.clip(1.0 * wash + 0.95 * dry + 0.55 * cun, 0, 1)
    total = total * (1 - mist) * (1 - 0.8 * bright_smooth)
    total = np.clip(total, 0, 1)
    # paper and ink colours; faint colour wash retains light ochre / blue-green
    paper = np.array([0.93, 0.89, 0.80], np.float32)
    fib = cv2.GaussianBlur(rng.standard_normal((h, w)).astype(np.float32), (0, 0), 0.8) * 0.015 + smooth_noise(h, w, 40, rng) * 0.015
    pap = paper[None, None] + fib[..., None]
    inkc = np.array([0.10, 0.09, 0.085], np.float32)
    col = cv2.GaussianBlur(rgb.astype(np.float32) / 255, (0, 0), 4)
    colg = col.mean(2, keepdims=True)
    tint = pap * (1 + 0.15 * (col - colg))
    base = tint * (1 - total[..., None]) + inkc * total[..., None]
    return np.clip(base, 0, 1)

# ---------------------------------------------------------------- van gogh
class VGTeacher:
    def __init__(self, device='cuda'):
        from adain_teacher import AdaINTeacher
        from data import image_tensor
        self.t = AdaINTeacher(ROOT).to(device).eval(); self.dev = device
        refs = ['data/references/vangogh/starry_night.jpg', 'data/references/vangogh/436535.jpg']
        self.stats = []
        with torch.no_grad():
            for r in refs:
                s = self.t.encoder(image_tensor(ROOT / r, (512, 384) if 'starry' in r else (512, 408)).unsqueeze(0).to(device))
                self.stats.append((s.mean((2, 3), keepdim=True), (s.var((2, 3), keepdim=True) + 1e-5).sqrt()))
    @torch.no_grad()
    def __call__(self, rgb, mix=0.45, alpha=1.0, chroma_keep=0.45):
        h, w = rgb.shape[:2]
        x = torch.from_numpy(rgb).permute(2, 0, 1)[None].float().to(self.dev) / 255
        H, W = (h + 7) // 8 * 8, (w + 7) // 8 * 8
        xp = torch.nn.functional.pad(x, (0, W - w, 0, H - h), mode='reflect')
        c = self.t.encoder(xp)
        cm = c.mean((2, 3), keepdim=True); cs = (c.var((2, 3), keepdim=True) + 1e-5).sqrt()
        sm = self.stats[0][0] * (1 - mix) + self.stats[1][0] * mix
        ss = self.stats[0][1] * (1 - mix) + self.stats[1][1] * mix
        t = (c - cm) / cs * ss + sm; t = t * alpha + c * (1 - alpha)
        y = self.t.decoder(t).clamp(0, 1)[:, :, :h, :w]
        y = (y[0].permute(1, 2, 0).cpu().numpy() * 255).astype(np.uint8)
        # partial chroma retention: keep VG luminance strokes, pull hue toward content
        ly = _lab(y); lx = _lab(cv2.bilateralFilter(rgb, 9, 30, 9))
        ly[..., 1:] = ly[..., 1:] * (1 - chroma_keep) + (128 + (lx[..., 1:] - 128) * 1.35) * chroma_keep
        ly[..., 0] = ly[..., 0] * 0.85 + lx[..., 0] * 0.15
        out = cv2.cvtColor(np.clip(ly, 0, 255).astype(np.uint8), cv2.COLOR_LAB2RGB)
        return out.astype(np.float32) / 255
