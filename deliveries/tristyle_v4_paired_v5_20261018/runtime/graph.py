"""Explicit operator graph for TriStyleV3 (shared + per-expert lists).
Ops: input, conv (relu flag fused), add, cat, nearest2, output. Same order as model.forward."""
from model import STYLES, CB

def build_graph(model):
    def emitter():
        ops = []
        def emit(op, id, inputs, **kw): ops.append(dict(op=op, id=id, inputs=list(inputs), **kw)); return id
        return ops, emit
    def conv(emit, mod, name, x):
        return emit('conv', name, [x], weight_key=name + '.conv', relu=mod.relu is not None and not _is_identity(mod.relu))
    shared, emit = emitter()
    x = emit('input', 'input', [], qparam_key='quant', format='RGB888', float_divisor=255)
    f1 = conv(emit, model.stem, 'stem', x)
    f2 = conv(emit, model.d2pw, 'd2pw', conv(emit, model.d2dw, 'd2dw', f1))
    f4 = conv(emit, model.d4pw, 'd4pw', conv(emit, model.d4dw, 'd4dw', f2))
    f8 = conv(emit, model.d8pw, 'd8pw', conv(emit, model.d8dw, 'd8dw', f4))
    experts = []
    for i, e in enumerate(model.experts):
        ops, emit = emitter(); p = f'experts.{i}'
        def stage(st, sname, xs):
            h = emit('cat', sname + '.cat', xs, qparam_key=sname + '.cat', axis=1) if len(xs) > 1 else xs[0]
            h = conv(emit, st.fuse, sname + '.fuse', h)
            for j, b in enumerate(st.blocks):
                bn = f'{sname}.blocks.{j}'
                z = conv(emit, b.expand, bn + '.expand', h)
                if b.kind == 'sq': z = conv(emit, b.dw, bn + '.dw', z)
                else: z = conv(emit, b.dwv, bn + '.dwv', conv(emit, b.dwh, bn + '.dwh', z))
                z = conv(emit, b.project, bn + '.project', z)
                h = emit('add', bn + '.add', [h, z], qparam_key=bn + '.add')
            return h
        h = stage(e.s8, p + '.s8', [f8])
        h = stage(e.s4, p + '.s4', [emit('nearest2', p + '.up8', [h]), f4])
        h = stage(e.s2, p + '.s2', [emit('nearest2', p + '.up4', [h]), f2])
        h = stage(e.s1, p + '.s1', [emit('nearest2', p + '.up2', [h]), f1])
        h = conv(emit, e.dw1, p + '.dw1', h); h = conv(emit, e.mix1, p + '.mix1', h); h = conv(emit, e.head, p + '.head', h)
        emit('output', p + '.output', [h], format='RGB888', clamp=[0, 1])
        experts.append(ops)
    return {'format': 'TRISTYLE_V3_GRAPH', 'styles': list(STYLES), 'input_multiple': 8, 'shared': shared, 'experts': experts,
            'style_switch': 'expert bank latched at admitted frame boundary only'}

def _is_identity(m):
    import torch.nn as nn
    return isinstance(m, nn.Identity)
