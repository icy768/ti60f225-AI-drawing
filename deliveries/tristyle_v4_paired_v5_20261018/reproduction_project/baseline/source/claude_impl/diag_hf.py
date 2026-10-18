"""Diagnose VG stroke underfit on validation: high-pass energy of student vs target vs content, and correlation."""
import sys, pathlib, numpy as np, torch
from torch.nn import functional as F
HERE = pathlib.Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
from train import Paired, highpass, oriented_energy
from model import TriStyleV3
ck = sys.argv[1]; tg = sys.argv[2]; dev = 'cpu'
m = TriStyleV3().eval(); m.load_state_dict(torch.load(ck, map_location='cpu', weights_only=False)['model'])
vd = Paired('validation', 256, [tg, 'ukiyoe2', 'ink34'])
b = torch.stack([vd[i] for i in range(0, len(vd), 6)]); x, t = b[:, 0], b[:, 1]
with torch.no_grad(): y = m(x, 0).clamp(0, 1)
hy, ht, hx = highpass(y), highpass(t), highpass(x)
corr = float((hy * ht).mean() / (hy.std() * ht.std() + 1e-8) / 1)
print('hp std student %.4f target %.4f content %.4f | corr(student,target) %.3f corr(content,target) %.3f' % (hy.std(), ht.std(), hx.std(), float(F.cosine_similarity(hy.flatten(1), ht.flatten(1)).mean()), float(F.cosine_similarity(hx.flatten(1), ht.flatten(1)).mean())))
oy, ot = oriented_energy(y), oriented_energy(t); print('oriented energy mean student %.4f target %.4f' % (oy.mean(), ot.mean()))
