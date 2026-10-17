"""Fixed-record DDR3 package: no JSON, zlib or float fields required by a loader.

Header64B (<8s14I), convolution descriptors80B (<20I), operator descriptors64B
(<16i), then16B-aligned integer arrays. Every three-style learned parameter,
integer requant constant, descriptor, header and alignment byte is counted.
This is a software-executable interface proposal, not implemented FPGA RTL.
"""
import argparse, hashlib, json, pathlib, struct, zlib
MAGIC = b'TRV3HW1\0'
OP = {'input': 0, 'conv': 1, 'add': 2, 'cat': 3, 'nearest2': 4, 'output': 5}
KINDS = {v: k for k, v in OP.items()}
HEADER = struct.Struct('<8s14I'); CONV = struct.Struct('<20I'); NODE = struct.Struct('<16i')


def write_hw(source, destination, width=640, height=480):
    blob = pathlib.Path(source).read_bytes(); _, nm, nb, nc, ver = struct.unpack('<8sIIII', blob[:24])
    assert ver == 3 and len(blob) == 24 + nm + nb
    meta = json.loads(zlib.decompress(blob[24:24 + nm])); old = blob[24 + nm:]
    if meta.get('integer_requant_version') != 1:
        from int_contract import attach_integer_constants
        attach_integer_constants(meta)
    body = bytearray(); conv_records = []; offsets = {}; align_bytes = 0
    totals = {'weight_int8': 0, 'bias_int32': 0, 'multiplier_int32': 0, 'exponent_int8': 0}
    for c in meta['convs']:
        ptr = {}
        for key, label in (('weight', 'weight_int8'), ('bias', 'bias_int32'), ('multiplier', 'multiplier_int32'), ('exponent', 'exponent_int8')):
            pad = (-len(body)) % 16; body.extend(bytes(pad)); align_bytes += pad
            off, size = c[key]; ptr[key] = len(body); body.extend(old[off:off + size]); totals[label] += size
        outc, ing, kh, kw = c['shape']; group = c['groups']
        conv_records.append(CONV.pack(ing * group, outc, kh, kw, *c['stride'], *c['padding'], group,
            int(c['relu']), c['in_zp'], c['out_zp'], ptr['weight'], ptr['bias'], ptr['multiplier'], ptr['exponent'], c.get('accumulator_absolute_bound', 0), 0, 0, 0))
        offsets[c['name']] = len(conv_records) - 1
    pad = (-len(body)) % 16; body.extend(bytes(pad)); align_bytes += pad
    shared = meta['graph']['shared']; experts = meta['graph']['experts']; nodes = shared + sum(experts, [])
    ids = {n['id']: i for i, n in enumerate(nodes)}; node_records = []
    for n in nodes:
        ins = n['inputs']; assert len(ins) <= 2
        a = [0] * 16; a[0] = OP[n['op']]; a[1:3] = [ids[x] for x in ins] + [-1] * (2 - len(ins)); a[3] = -1
        if n['op'] == 'conv': a[3] = offsets[n['weight_key']]
        r = n.get('integer', {})
        if n['op'] in ('input', 'output'):
            a[4:7] = [r['multiplier'], r['exponent'], r.get('in_zp', 0)]; a[10] = r.get('out_zp', 0)
        if n['op'] in ('add', 'cat'):
            for j, q in enumerate(r['inputs']): a[4 + 3 * j:7 + 3 * j] = [q['multiplier'], q['exponent'], q['in_zp']]
            a[10:12] = [r['out_zp'], r['guard_bits']]
        a[12] = len(ins); node_records.append(NODE.pack(*a))
    oc = HEADER.size; on = oc + len(conv_records) * CONV.size; ob = on + len(node_records) * NODE.size
    total = ob + len(body)
    hdr = HEADER.pack(MAGIC, 1, total, len(conv_records), len(nodes), len(shared), *map(len, experts), oc, on, ob, len(body), width, height)
    result = hdr + b''.join(conv_records) + b''.join(node_records) + body
    assert len(result) == total
    pathlib.Path(destination).write_bytes(result)
    report = {**totals, 'header': HEADER.size, 'conv_descriptors': len(conv_records) * CONV.size,
              'operator_descriptors': len(nodes) * NODE.size, 'alignment_padding': align_bytes, 'total_bytes': total,
              'limit': 500000, 'fits': total <= 500000, 'sha256': hashlib.sha256(result).hexdigest(),
              'convs': len(conv_records), 'nodes': len(nodes), 'shared_nodes': len(shared), 'expert_nodes': list(map(len, experts)),
              'default_size': [width, height], 'note': 'All-three standalone deployment alternative; do not deploy both this and the JSON pack. Fixed-record software contract; RTL loader/engine not implemented.'}
    assert sum(report[k] for k in ('weight_int8', 'bias_int32', 'multiplier_int32', 'exponent_int8', 'header', 'conv_descriptors', 'operator_descriptors', 'alignment_padding')) == total
    return report


def parse_hw(blob):
    h = HEADER.unpack_from(blob); magic, version, total, nc, nn, ns, n0, n1, n2, oc, on, ob, nb, w, ht = h
    assert magic == MAGIC and version == 1 and total == len(blob) and ob + nb == total and ns + n0 + n1 + n2 == nn
    convs = []
    for i in range(nc):
        a = CONV.unpack_from(blob, oc + CONV.size * i)
        cin, cout, kh, kw, sh, sw, ph, pw, groups, flags, zi, zo, ow, obi, om, oe, bound = a[:17]
        assert cin % groups == 0
        convs.append({'name': f'conv{i}', 'shape': [cout, cin // groups, kh, kw], 'stride': [sh, sw], 'padding': [ph, pw],
            'groups': groups, 'relu': bool(flags & 1), 'in_zp': zi, 'out_zp': zo, 'in_scale': 1., 'out_scale': 1.,
            'weight': [ow, cout * (cin // groups) * kh * kw], 'bias': [obi, cout * 4], 'multiplier': [om, cout * 4],
            'exponent': [oe, cout], 'accumulator_absolute_bound': bound})
    nodes = []; qp = {}
    for i in range(nn):
        a = NODE.unpack_from(blob, on + NODE.size * i); op = KINDS[a[0]]
        n = {'op': op, 'id': f'n{i}', 'inputs': [f'n{j}' for j in a[1:3] if j >= 0]}
        assert len(n['inputs']) == a[12]
        if op == 'conv': n['weight_key'] = convs[a[3]]['name']
        elif op == 'input':
            n['integer'] = {'multiplier': a[4], 'exponent': a[5], 'out_zp': a[10]}; qp['quant'] = [1., a[10]]
        elif op == 'output': n['integer'] = {'multiplier': a[4], 'exponent': a[5], 'in_zp': a[6]}
        elif op in ('add', 'cat'):
            n['qparam_key'] = n['id']; qp[n['id']] = [1., a[10]]
            n['integer'] = {'out_zp': a[10], 'guard_bits': a[11], 'inputs': [
                {'multiplier': a[4 + 3 * j], 'exponent': a[5 + 3 * j], 'in_zp': a[6 + 3 * j]} for j in range(a[12])]}
        nodes.append(n)
    at = ns; experts = []
    for n in (n0, n1, n2): experts.append(nodes[at:at + n]); at += n
    meta = {'format': 'TRISTYLE_V3_FIXED_INTEGER', 'integer_requant_version': 1, 'convs': convs, 'qparams': qp,
            'styles': ['vangogh', 'ukiyoe', 'ink'], 'default_size': [w, ht], 'diagnostic_scales': 'omitted: dummy1 fields for interpreter tuple bookkeeping only',
            'graph': {'shared': nodes[:ns], 'experts': experts}}
    return meta, memoryview(blob)[ob:ob + nb]


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('source'); ap.add_argument('output'); ap.add_argument('--width', type=int, default=640); ap.add_argument('--height', type=int, default=480)
    a = ap.parse_args(); report = write_hw(a.source, a.output, a.width, a.height)
    pathlib.Path(a.output).with_suffix('.bytes.json').write_text(json.dumps(report, indent=2)); print(json.dumps(report, indent=2))
