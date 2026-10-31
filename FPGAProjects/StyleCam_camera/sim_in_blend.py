"""Style blend RTL check: sc_in_refresh with blend_style/blend_alpha against the unmodified module
(git 53606e2) fed with Python-blended IN constants. All 12 layers, coefficient words bit-exact."""
from pathlib import Path
import json, os, random, subprocess
from compact_in_constants import compact

ROOT = Path(__file__).resolve().parent
OUT = ROOT/'validation/in_blend_20261031'; OUT.mkdir(parents=True, exist_ok=True)
BIN = Path(os.environ.get('ICARUS_BIN', ROOT.parent/'tools/iverilog/mingw64/bin'))
REF_COMMIT = '53606e2'
M56, M61, M72 = (1 << 56) - 1, (1 << 61) - 1, (1 << 72) - 1
sgn = lambda v, n: v - (1 << n) if v >> (n - 1) & 1 else v


def blended_words(words, a, b, alpha):
    out = list(words)
    for layer in range(12):
        for ch in range(16 if layer in (0, 11) else 24):
            ia, ib = a*288 + layer*24 + ch, b*288 + layer*24 + ch
            wa, wb = words[ia], words[ib]
            ga, gb = sgn((wa >> 232) & M72, 72) >> 4, sgn((wb >> 232) & M72, 72) >> 4   # 61-bit mantissas
            ba, bb = sgn((wa >> 136) & M56, 56), sgn((wb >> 136) & M56, 56)
            g = ga + ((gb - ga)*alpha >> 3)          # floor, as the RTL's arithmetic shift
            be = ba + ((bb - ba)*alpha >> 3)
            eps = wa & ((1 << 136) - 1)
            out[ia] = ((((g << 4) & M72) << 40) << 192) | ((be & M56) << 136) | eps
    return out


def stats_file(path):
    rng = random.Random(20261031); lines = []
    for layer in range(12):
        n = 320*240 if layer == 0 or layer >= 10 else 160*120
        for ch in range(24):
            m = rng.randint(-3000, 3000); v = rng.randint(50, 4_000_000)
            s1 = (m*n) & ((1 << 40) - 1); s2 = (v + m*m)*n
            assert s2 < (1 << 60)
            lines.append(f'{(s1 << 60) | s2:025x}')
    path.write_text('\n'.join(lines) + '\n')


words = [int(v, 16) for v in (ROOT/'model/in_constants.mem').read_text().split()]
ref_src = subprocess.run(['git', 'show', f'{REF_COMMIT}:FPGAProjects/StyleCam_camera/rtl/sc_in_refresh.v'], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout.replace('module sc_in_refresh', 'module sc_in_refresh_ref')
(OUT/'sc_in_refresh_ref.v').write_text(ref_src)
stats_file(OUT/'stats.hex')
cases = [(0, 1, 0), (0, 1, 1), (0, 1, 4), (0, 1, 7), (0, 1, 8), (1, 2, 3), (1, 2, 8), (2, 0, 5), (2, 1, 6), (1, 0, 2)]
results = {}
for a, b, alpha in cases:
    name = f's{a}_b{b}_a{alpha}'; ref = OUT/name/'constants.mem'; ref.parent.mkdir(exist_ok=True)
    ref.write_text('\n'.join(f'{w:076x}' for w in blended_words(words, a, b, alpha)) + '\n')
    compact(ref)
    exe = OUT/name/'tb.vvp'
    subprocess.run([str(BIN/'iverilog.exe'), '-g2012', '-s', 'in_blend_tb', f'-Pin_blend_tb.STYLE={a}', f'-Pin_blend_tb.BSTYLE={b}',
                    f'-Pin_blend_tb.ALPHA={alpha}', f'-Pin_blend_tb.REFFILE="{ref.relative_to(ROOT).as_posix()}"',
                    f'-Pin_blend_tb.STATS="{(OUT/"stats.hex").relative_to(ROOT).as_posix()}"', '-o', str(exe),
                    'sim/in_blend_tb.v', 'rtl/sc_in_refresh.v', str(OUT/'sc_in_refresh_ref.v'), 'rtl/sc_in_math.v', 'rtl/sc_in_alu.v',
                    'rtl/common.v'], cwd=ROOT, check=True)
    r = subprocess.run([str(BIN/'vvp.exe'), str(exe)], cwd=ROOT, capture_output=True, text=True)
    print(name, r.stdout.strip(), flush=True)
    assert r.returncode == 0 and 'PASS' in r.stdout, r.stdout + r.stderr
    results[name] = r.stdout.strip()
    for f in ref.parent.iterdir(): f.unlink()
    ref.parent.rmdir()
(OUT/'result.json').write_text(json.dumps({'reference_commit': REF_COMMIT, 'cases': results}, indent=2), encoding='utf-8')
print('PASS style blend: all cases bit-exact against the reference module')
