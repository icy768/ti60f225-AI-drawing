import sys, pathlib, json, numpy as np, torch
HERE = pathlib.Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
from quantize import calibrate, to_int, pack
from model import TriStyleV3
from int_ref import IntGraph
import int_ref
torch.backends.quantized.engine = 'onednn'; torch.set_num_threads(4)
ck = sys.argv[1]; tmp = pathlib.Path(sys.argv[2]); tmp.mkdir(parents=True, exist_ok=True)
fp = TriStyleV3().eval(); fp.load_state_dict(torch.load(ck, map_location='cpu', weights_only=False)['model'])
qi = to_int(calibrate(fp)); pack(qi, TriStyleV3(), tmp / 'p.bin')
outs = {}
for n, m in qi.named_modules():
    if isinstance(m, (torch.ao.nn.quantized.Conv2d,)):
        m.register_forward_hook(lambda mod, a, o, k=n: outs.__setitem__(k[:-5] if k.endswith('.conv') else k, o.int_repr().long()))
    if isinstance(m, torch.ao.nn.quantized.QFunctional):
        def wrap(f, k):
            def g(*a, **kw):
                o = f(*a, **kw); outs[k] = o.int_repr().long(); return o
            return g
        m.add = wrap(m.add, n); m.cat = wrap(m.cat, n)
from PIL import Image as _I
x = torch.from_numpy(np.array(_I.open('data/test/water_day.png').convert('RGB').resize((160, 120)))).permute(2, 0, 1)[None].contiguous()
style = int(sys.argv[3]) if len(sys.argv) > 3 else 0
with torch.no_grad(): qi(x.float() / 255, style)
g = IntGraph(tmp / 'p.bin'); trace = {}
orig = g.conv
nodes = g.meta['graph']['shared'] + g.meta['graph']['experts'][style]
# replay manually with per-node comparison, feeding the reference its OWN values (error accumulation) and also isolated
v = {}
for n in nodes:
    pass
# simple instrumented run
import types
cmp = []
def run():
    vv = {}
    for n in nodes:
        op, k, ins = n['op'], n['id'], n['inputs']
        if op == 'input':
            s, z = g.qp['quant']; m, e = int_ref.q31(1 / (255 * s)); vv[k] = ((int_ref.rshift_rne(x.to(torch.int64) * m, 31 - e) + z).clamp(0, 255), (s, z))
        elif op == 'conv':
            key = n['weight_key'][:-5]
            # isolated: feed torch's input if available
            src = ins[0]; srckey = src if src in outs else None
            vv[k] = g.conv(g.c[n['weight_key']], vv[src][0])
            if key in outs:
                iso = g.conv(g.c[n['weight_key']], outs[srckey] if srckey else vv[src][0])[0]
                cmp.append((k, int((vv[k][0] - outs[key]).abs().max()), int((iso - outs[key]).abs().max()), float((iso - outs[key]).abs().float().mean())))
        elif op in ('add', 'cat'):
            s, z = g.qp[n['qparam_key']]; terms = []; isoterms = []
            for i in ins:
                a, (si, zi) = vv[i]; m, e = int_ref.q31(si / s * 65536); terms.append(int_ref.rshift_rne((a - zi) * m, 31 - e))
                ai = outs.get(i, a); isoterms.append(int_ref.rshift_rne((ai - zi) * m, 31 - e))
            t = terms[0] + terms[1] if op == 'add' else torch.cat(terms, 1); ti = isoterms[0] + isoterms[1] if op == 'add' else torch.cat(isoterms, 1)
            vv[k] = ((int_ref.rshift_rne(t, 16) + z).clamp(0, 255), (s, z)); iso = (int_ref.rshift_rne(ti, 16) + z).clamp(0, 255)
            key = n['qparam_key']
            if key in outs: cmp.append((k, int((vv[k][0] - outs[key]).abs().max()), int((iso - outs[key]).abs().max()), float((iso - outs[key]).abs().float().mean())))
        elif op == 'nearest2':
            a, q = vv[ins[0]]; vv[k] = (a.repeat_interleave(2, 2).repeat_interleave(2, 3), q)
            if ins[0] in outs: outs[k] = outs[ins[0]].repeat_interleave(2, 2).repeat_interleave(2, 3)
        # map conv node ids to their torch outputs for isolated feeding
        if op == 'conv' and n['weight_key'][:-5] in outs: outs[k] = outs[n['weight_key'][:-5]]
run()
for c in cmp: print(c)
