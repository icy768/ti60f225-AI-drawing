"""Offline quantization-parameter compilation. The frame datapath uses integers only.

Float scales remain optional diagnostic metadata; all input/output/add/cat ratios
are compiled to Q31 constants inside new deployment packs. No student topology
or learned weights are imported here.
"""
import math


def q31(r):
    f, e = math.frexp(float(r)); m = round(f * (1 << 31))
    if m == 1 << 31: m //= 2; e += 1
    return int(m), int(e)


def attach_integer_constants(meta):
    convs = {c['name']: c for c in meta['convs']}
    for expert in meta['graph']['experts']:
        scales = {}
        for n in meta['graph']['shared'] + expert:
            op, k, ins = n['op'], n['id'], n['inputs']
            if op == 'input':
                s, z = meta['qparams']['quant']; m, e = q31(1 / (255 * s))
                n['integer'] = {'multiplier': m, 'exponent': e, 'out_zp': int(z)}
                scales[k] = (s, z)
            elif op == 'conv':
                c = convs[n['weight_key']]; scales[k] = (c['out_scale'], c['out_zp'])
            elif op == 'nearest2': scales[k] = scales[ins[0]]
            elif op in ('add', 'cat'):
                s, z = meta['qparams'][n['qparam_key']]; rows = []
                for parent in ins:
                    si, zi = scales[parent]; m, e = q31(si / s * 65536)
                    rows.append({'multiplier': m, 'exponent': e, 'in_zp': int(zi)})
                n['integer'] = {'inputs': rows, 'out_zp': int(z), 'guard_bits': 16}; scales[k] = (s, z)
            elif op == 'output':
                s, z = scales[ins[0]]; m, e = q31(255 * s)
                n['integer'] = {'multiplier': m, 'exponent': e, 'in_zp': int(z)}
            else: raise ValueError(op)
    meta['integer_requant_version'] = 1
    return meta
