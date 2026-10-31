"""Phone preview tap in all six display layouts (0..2 normal, 3..5 Resize demo): every preview
pixel of a full frame must be the exact dithered 4x4 mean of the 640x480 picture."""
from pathlib import Path
import json, os, subprocess
ROOT = Path(__file__).resolve().parent
OUT = ROOT/'validation/stream_tap_layouts'; OUT.mkdir(parents=True, exist_ok=True)
BIN = Path(os.environ.get('ICARUS_BIN', ROOT.parent/'tools/iverilog/mingw64/bin'))
BAYER = [0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5]
def src(sx, sy): return ((sx*7+sy*3) & 255, (sx*2+sy*9+17) & 255, ((sx >> 1) ^ sy) & 255)
def expected():
    words = []
    for band in (0, 1):
        for gy in range(band, 120, 2):
            for gx in range(160):
                s = [0, 0, 0]
                for dy in range(4):
                    for dx in range(4):
                        for c, v in enumerate(src(4*gx+dx, 4*gy+dy)): s[c] += v
                a = [v >> 4 for v in s]; t = BAYER[(gy & 3)*4 + (gx & 3)]
                q = [min((a[0]+2*t) >> 5, 7), min((a[1]+2*t) >> 5, 7), min((a[2]+4*t) >> 6, 3)]
                words.append(band << 8 | q[0] << 5 | q[1] << 2 | q[2])
    return words
want = expected(); results = {}
for mode in range(6):
    exe, txt = OUT/f'mode{mode}.vvp', OUT/f'mode{mode}.txt'
    subprocess.run([str(BIN/'iverilog.exe'), '-g2012', '-s', 'stream_tap_layout_tb', f'-Pstream_tap_layout_tb.MODE={mode}',
                    f'-Pstream_tap_layout_tb.OUT="{txt.as_posix()}"', '-o', str(exe), 'sim/stream_tap_layout_tb.v', 'rtl/sc_stream_tap.v'],
                   cwd=ROOT, check=True)
    r = subprocess.run([str(BIN/'vvp.exe'), str(exe)], cwd=ROOT, capture_output=True, text=True)
    got = [int(l, 16) for l in txt.read_text().split()]
    bad = sum(g != w for g, w in zip(got, want)) + abs(len(got) - len(want))
    print(f'mode {mode}: {r.stdout.strip()} mismatches={bad}', flush=True)
    assert r.returncode == 0 and bad == 0 and 'drops=0' in r.stdout, r.stdout + r.stderr
    results[mode] = {'passed': True, 'words': len(got)}
    exe.unlink(); txt.unlink()
(OUT/'result.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
print('PASS preview tap: all six layouts pixel-exact')
