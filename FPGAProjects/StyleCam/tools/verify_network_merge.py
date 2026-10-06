"""Verify paired network artifacts and the merged driver without board changes."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'algo'))

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--workdir', required=True)
    ap.add_argument('--gcc', required=True)
    args = ap.parse_args()
    wd = Path(args.workdir).resolve()
    wd.mkdir(parents=True, exist_ok=False)
    exp = ROOT / 'rtl/gen/v21b_ukiyoe_qat900_640x480'
    info = json.loads((exp / 'export.json').read_text(encoding='utf-8'))
    assert sha(ROOT / 'runs/art_styles_c24_v21b_ukiyoe_qat900_soft15/student.pt') == info['checkpoint_sha256']
    assert sha(exp / 'net_blob.bin') == info['blob_sha256']
    blob = (exp / 'net_blob.bin').read_bytes()
    words = struct.unpack('<' + 'I' * (len(blob) // 4), blob)
    assert words[:4] == (0x53544e31, 4050, 3, 0)
    assert len(words) == 4 + 3 * words[1]
    text = (ROOT / 'sw/net_blob.h').read_text(encoding='utf-8')
    body = text.split('net_blob[NET_BLOB_WORDS] = {', 1)[1].split('};', 1)[0]
    assert tuple(int(x, 16) for x in re.findall(r'0x[0-9a-fA-F]+', body)) == words
    ns = {'efx': 'http://www.efinixinc.com/enf_proj'}
    tree = ET.parse(ROOT / 'syn/vision_map.xml')
    for node in tree.findall('efx:design_info/efx:design_file', ns):
        assert (ROOT / 'syn' / node.get('name')).is_file(), node.attrib
    print('ARTIFACT PAIRING PASS', flush=True)
    exe = wd / 'network_guard.exe'
    cmd = [args.gcc, '-O2', '-Wall', '-DVISION_HOST_TEST', '-I' + str(ROOT / 'sw'),
           str(ROOT / 'sw/test/network_blob_guard_test.c'), str(ROOT / 'sw/vision.c'), '-lm', '-o', str(exe)]
    p = subprocess.run(cmd, capture_output=True)
    (wd / 'gcc_guard.log').write_bytes(p.stdout + p.stderr)
    p.check_returncode()
    subprocess.run([str(exe)], check=True)
    print('FIRMWARE BLOB GUARDS PASS', flush=True)
    import numpy as np
    from PIL import Image
    import torch
    import golden
    import gen_rtl
    torch.set_num_threads(4)
    q = golden.load(str(exp / 'qparams'))
    assert q['styles'] == ['van_gogh', 'ukiyo_e', 'ink_landscape']
    banks = []
    for i, layer in enumerate(q['layers']):
        h = [int(x, 16) for x in (exp / f"c{i}_{layer['name']}.mem").read_text().splitlines()]
        z = np.array([h[j] | (h[j + 1] << 19) for j in range(0, len(h), 2)], np.int64).reshape(6, layer['cout'])
        m, b = (z >> 20) & 262143, z & 1048575
        banks.append((np.where(m & 131072, m - 262144, m), np.where(b & 524288, b - 1048576, b)))
    regenerated = wd / 'regenerated'
    gen_rtl.generate(q, 640, 480, str(regenerated), banks, 6, relative_mem=True)
    for f in regenerated.iterdir():
        if f.suffix == '.mem' or f.name in ('cfg.txt', 'stylenet_top.v'):
            assert f.read_bytes() == (exp / f.name).read_bytes(), f.name
    print('REGENERATED NETWORK RTL/MEM PASS', flush=True)
    img = np.asarray(Image.open(ROOT / 'samples/input.png').convert('RGB')).copy()
    checked = []
    for s, name in enumerate(q['styles']):
        out, _, _ = golden.run(q, img, s)
        expected = np.asarray(Image.open(ROOT / 'samples' / (name + '_int.png')))
        assert np.array_equal(out, expected), name
        checked.append(name)
        print('INTEGER SAMPLE EXACT PASS', name, flush=True)
    report = dict(passed=True, paired_artifacts=True, firmware_blob_guards=True,
                  regenerated_rtl_mem_exact=True, integer_sample_exact=checked,
                  rtl_simulated=False, board_tested=False,
                  source_commit='42452f5ebb7f5f05fcac4753ca86af70a2fd4f9e')
    (wd / 'verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('NETWORK MERGE CHECK PASS', flush=True)

if __name__ == '__main__':
    main()
