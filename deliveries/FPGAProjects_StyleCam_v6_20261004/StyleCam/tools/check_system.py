"""Run the packaged v6 contract through the reduced synthetic system fixture."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--workdir', required=True)
    ap.add_argument('--iverilog', required=True)
    ap.add_argument('--vvp', required=True)
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    stage = Path(args.workdir).resolve()
    if not str(stage).isascii():
        raise ValueError('Use an ASCII workdir')
    stage.mkdir(parents=True, exist_ok=False)
    for name in ('sim', 'rtl', 'algo'):
        shutil.copytree(root / name, stage / name, ignore=shutil.ignore_patterns('work', '__pycache__'))
    (stage / 'docs').mkdir()
    shutil.copy2(root / 'samples/input.png', stage / 'input.png')
    env = dict(os.environ, IVERILOG=args.iverilog, VVP=args.vvp, PYTHONIOENCODING='utf-8')
    env['PATH'] = str(Path(args.iverilog).parent) + os.pathsep + env['PATH']
    cmd = [sys.executable, '-X', 'utf8', '-u', str(stage / 'sim/run_sys.py'),
           '--contract', str(stage / 'rtl/gen/v6_cal100_640x480/qparams'), '--image', str(stage / 'input.png')]
    r = subprocess.run(cmd, cwd=stage, env=env, capture_output=True, timeout=300)
    (stage / 'system.log').write_bytes(r.stdout + r.stderr)
    print(r.stdout.decode('utf-8', errors='replace'))
    r.check_returncode()
    if '整链路 PASS' not in r.stdout.decode('utf-8', errors='replace'):
        raise RuntimeError('Missing system PASS')


if __name__ == '__main__':
    main()
