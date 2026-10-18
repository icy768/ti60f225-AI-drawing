"""Do the stroke components (target - abstraction of content) appear in the student? Band 4-16 px."""
import sys, pathlib, numpy as np, torch
from torch.nn import functional as F
HERE = pathlib.Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
from train import Paired
from model import TriStyleV3
def band(z, a=2, b=8):
    g = lambda s: F.avg_pool2d(F.pad(z, (s, s, s, s), mode='reflect'), 2 * s + 1, 1)
    return g(a) - g(b)
ck = sys.argv[1]; tg = sys.argv[2]
m = TriStyleV3().eval(); m.load_state_dict(torch.load(ck, map_location='cpu', weights_only=False)['model'])
vd = Paired('validation', 256, [tg, 'ukiyoe2', 'ink34']); b = torch.stack([vd[i] for i in range(0, len(vd), 6)]); x, t = b[:, 0], b[:, 1]
with torch.no_grad(): y = m(x, 0).clamp(0, 1)
bx, bt, by = band(x), band(t), band(y)
# stroke residual: part of target band not explained by content band (least squares per image)
k = (bt * bx).sum((1, 2, 3), keepdim=True) / (bx * bx).sum((1, 2, 3), keepdim=True); rt = bt - k * bx
ky = (by * bx).sum((1, 2, 3), keepdim=True) / (bx * bx).sum((1, 2, 3), keepdim=True); ry = by - ky * bx
cs = F.cosine_similarity(ry.flatten(1), rt.flatten(1)).mean()
print('mid band std: content %.4f target %.4f student %.4f | stroke-residual std target %.4f student %.4f | cos(stroke residuals) %.3f' % (bx.std(), bt.std(), by.std(), rt.std(), ry.std(), cs))
