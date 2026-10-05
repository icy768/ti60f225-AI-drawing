"""Exercise SC431HAI RAW10 RTL at VGA-producing geometry (synthetic data)."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--workdir', required=True)
    ap.add_argument('--iverilog', required=True)
    ap.add_argument('--vvp', required=True)
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    wd = Path(args.workdir).resolve()
    if not str(wd).isascii():
        raise ValueError('Use an ASCII workdir')
    wd.mkdir(parents=True, exist_ok=False)
    (wd / 'sim').mkdir()
    (wd / 'rtl').mkdir()
    shutil.copy2(root / 'sim/run_rawbin.py', wd / 'sim/run_rawbin.py')
    for name in ('raw_bin3.v', 'common.v', 'axi_frame.v'):
        shutil.copy2(root / 'rtl' / name, wd / 'rtl' / name)
    os.environ['IVERILOG'], os.environ['VVP'] = args.iverilog, args.vvp
    os.environ['PATH'] = str(Path(args.iverilog).parent) + os.pathsep + os.environ['PATH']
    sys.path.insert(0, str(wd / 'sim'))
    import run_rawbin
    cases = [(24, 9, 2, 0, 0, (256, 256, 256)), (24, 9, 2, 1, 1, (280, 255, 350)),
             (36, 12, 2, 0, 2, (512, 300, 200)), (48, 18, 2, 1, 3, (256, 256, 256)),
             (1920, 1440, 1, 0, 0, (256, 256, 256))]
    results = [dict(case=c, pass_check=run_rawbin.run(*c, seed=i + 1)) for i, c in enumerate(cases)]
    (wd / 'camera_frontend.json').write_text(json.dumps(dict(cases=results,
        physical_camera=False, pass_check=all(r['pass_check'] for r in results)), indent=2), encoding='utf-8')
    if not all(r['pass_check'] for r in results):
        raise RuntimeError('RAW10 frontend mismatch')


if __name__ == '__main__':
    main()
