"""Check the delivered contract using local sample frames; no dataset required."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'algo'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--workdir', required=True, help='New ASCII-only output directory')
    ap.add_argument('--rtl', action='store_true')
    ap.add_argument('--vga', action='store_true')
    ap.add_argument('--verilator', action='store_true')
    ap.add_argument('--verilator-root', help='Verilator installation directory containing bin and include')
    ap.add_argument('--compiler-bin', help='Directory containing g++, ar and make for Verilator')
    ap.add_argument('--gcc', default=shutil.which('gcc'))
    ap.add_argument('--iverilog', default=shutil.which('iverilog'))
    ap.add_argument('--vvp', default=shutil.which('vvp'))
    args = ap.parse_args()
    wd = Path(args.workdir).resolve()
    if not str(wd).isascii():
        raise ValueError('Use an ASCII-only workdir for RTL tools')
    wd.mkdir(parents=True, exist_ok=False)
    exp = ROOT / 'rtl/gen/v21b_ukiyoe_qat900_640x480'
    ckpath = ROOT / 'runs/art_styles_c24_v21b_ukiyoe_qat900_soft15/student.pt'
    info = json.loads((exp / 'export.json').read_text(encoding='utf-8'))
    assert sha(ckpath) == info['checkpoint_sha256']
    assert sha(exp / 'net_blob.bin') == info['blob_sha256']
    assert info['styles'] == ['van_gogh', 'ukiyo_e', 'ink_landscape']
    blob = (exp / 'net_blob.bin').read_bytes()
    words = struct.unpack('<' + 'I' * (len(blob) // 4), blob)
    assert words[:4] == (0x53544e31, 4050, 3, 0)
    assert len(words) == 4 + 3 * words[1]
    header = (ROOT / 'sw/net_blob.h').read_text(encoding='utf-8')
    body = header.split('net_blob[NET_BLOB_WORDS] = {', 1)[1].split('};', 1)[0]
    assert tuple(int(h, 16) for h in re.findall(r'0x[0-9a-fA-F]+', body)) == words
    ns = {'efx': 'http://www.efinixinc.com/enf_proj'}
    tree = ET.parse(ROOT / 'syn/vision_map.xml')
    for node in tree.findall('efx:design_info/efx:design_file', ns):
        assert (ROOT / 'syn' / node.get('name')).is_file(), node.attrib
    # Pure file checks above also detect accidental cross-version firmware.
    import numpy as np
    import torch
    from PIL import Image
    import gen_rtl
    import golden
    from pc_validate import rtl_case, firmware, blob_check, metric
    from pc_extra_validate import initial_banks, simulate_verilator
    from tinystyle import TinyStyleNet, QCfg
    torch.set_num_threads(4)
    QCfg.enabled = QCfg.observe = False
    q = golden.load(str(exp / 'qparams'))
    banks = initial_banks(q, exp)
    regenerated = wd / 'regenerated'
    gen_rtl.generate(q, 640, 480, str(regenerated), banks, 6, relative_mem=True)
    for f in regenerated.iterdir():
        if f.suffix == '.mem' or f.name in ('cfg.txt', 'stylenet_top.v'):
            assert f.read_bytes() == (exp / f.name).read_bytes(), f.name
    ck = torch.load(ckpath, map_location='cpu', weights_only=False)
    net = TinyStyleNet(**ck['cfg']).eval()
    net.load_state_dict(ck['sd'])
    img = np.asarray(Image.open(ROOT / 'samples/input.png').convert('RGB')).copy()
    res = dict(checkpoint_sha256=sha(ckpath), blob=blob_check(q, exp),
               generated_contract_exact=True, quality=[], firmware=[], rtl=[])
    sw = wd / 'sw'
    sw.mkdir()
    for name in ('vision.c', 'vision.h', 'hal.h', 'board_profile.h', 'in_params.h', 'net_blob.h',
                 'main.c', 'sc431hai.c', 'sc431hai.h'):
        shutil.copy2(ROOT / 'sw' / name, sw / name)
    shutil.copy2(ROOT / 'sw/test/host_test.c', sw / 'host_test.c')
    shutil.copy2(ROOT / 'sw/test/delivery_guard_test.c', sw / 'delivery_guard_test.c')
    if args.gcc:
        r = subprocess.run([args.gcc, '-O2', '-Wall', '-D__USE_MINGW_ANSI_STDIO=1',
                            '-DVISION_HOST_TEST', '-I.', 'host_test.c', 'vision.c', '-lm',
                            '-o', 'host_test.exe'], cwd=sw, capture_output=True)
        (wd / 'gcc_host.log').write_bytes(r.stdout + r.stderr)
        r.check_returncode()
        r = subprocess.run([args.gcc, '-O2', '-Wall', '-DVISION_HOST_TEST', '-I.',
                            'delivery_guard_test.c', 'vision.c', '-lm', '-o', 'guard_test.exe'],
                           cwd=sw, capture_output=True)
        (wd / 'gcc_guard.log').write_bytes(r.stdout + r.stderr)
        r.check_returncode()
        r = subprocess.run([str(sw / 'guard_test.exe')], cwd=sw, capture_output=True)
        (wd / 'guard_test.log').write_bytes(r.stdout + r.stderr)
        r.check_returncode()
        for camera in (1,):
            r = subprocess.run([args.gcc, '-std=c11', '-Wall', '-fsyntax-only',
                                '-I.', 'main.c', 'sc431hai.c'], cwd=sw, capture_output=True)
            (wd / ('gcc_main_camera%d.log' % camera)).write_bytes(r.stdout + r.stderr)
            r.check_returncode()
    for s, name in enumerate(q['styles']):
        out, stats, _ = golden.run(q, img, s)
        expected = np.asarray(Image.open(ROOT / 'samples' / (name + '_int.png')))
        assert np.array_equal(out, expected), name
        with torch.no_grad():
            y = net(torch.from_numpy(img).permute(2, 0, 1)[None].float() / 255, torch.tensor([s]))
        fp = (y[0].permute(1, 2, 0).clamp(0, 1).numpy() * 255).round().astype(np.uint8)
        res['quality'].append(dict(style=name, sample_exact=True, **metric(out, fp)))
        if args.gcc:
            res['firmware'].append(dict(style=name, **firmware(q, stats, s, sw)))
        print('SAMPLE PASS', name, flush=True)
    if args.rtl:
        rtl = wd / 'rtl'
        shutil.copytree(ROOT / 'rtl', rtl, ignore=shutil.ignore_patterns('gen'))
        gen_rtl.RTL = str(rtl)
        if args.verilator:
            if args.verilator_root:
                os.environ['STYLECAM_VERILATOR_ROOT'] = str(Path(args.verilator_root).resolve())
            if args.compiler_bin:
                os.environ['STYLECAM_COMPILER_BIN'] = str(Path(args.compiler_bin).resolve())
            gen_rtl.simulate = simulate_verilator
            os.environ['STYLECAM_SIMULATOR'] = 'Verilator'
        else:
            assert args.iverilog and args.vvp, 'Supply --iverilog and --vvp or select --verilator'
            gen_rtl.IVERILOG, gen_rtl.VVP = args.iverilog, args.vvp
        frame = img if args.vga else np.asarray(Image.fromarray(img).resize((48, 32))).copy()
        for s in range(3):
            res['rtl'].append(rtl_case(q, frame, s, wd / ('rtl_style%d' % s), stat_layer=[0, 5, 10][s]))
        case = wd / 'rtl_serialized_switch'
        small = np.asarray(Image.fromarray(img).resize((48, 32))).copy()
        res['rtl'].append(rtl_case(q, small, 0, case, fixed_coefs=banks, switch=True, stat_layer=5))
        assert (case / 'cfg.txt').read_bytes() == (exp / 'cfg.txt').read_bytes()
    res.update(pass_check=True, board_verified=False, full_board_bitstream_available=False,
               firmware_host_checked=bool(args.gcc), rtl_checked=args.rtl,
               limits=['Dynamic IN oracle does not simulate refresh latency',
                       'No physical camera/DDR/HDMI or timing acceptance'])
    res['source_sha256'] = {str(f.relative_to(ROOT)).replace('\\', '/'): sha(f)
                            for d in ('rtl', 'sw') for f in (ROOT / d).rglob('*')
                            if f.is_file() and f.suffix in ('.v', '.h', '.c', '.mem')}
    (wd / 'verification.json').write_text(json.dumps(res, indent=2), encoding='utf-8')
    print('DELIVERY PC CHECK PASS; board acceptance still required', flush=True)


if __name__ == '__main__':
    main()
