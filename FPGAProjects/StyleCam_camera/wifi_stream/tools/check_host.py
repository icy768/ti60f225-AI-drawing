"""Portable host checks for the shipped ESP32 bridge; no ESP32 SDK required."""
from pathlib import Path
import os, shutil, subprocess, sys, tempfile

HERE = Path(__file__).resolve().parent
STUB = HERE / 'host_stub'
GXX = os.environ.get('GXX') or shutil.which('g++')
if not GXX:
    raise SystemExit('Set GXX to the host g++ compiler path.')
env = dict(os.environ)
env['PATH'] = str(Path(GXX).parent) + os.pathsep + env.get('PATH', '')
flags = [GXX, '-std=gnu++17', '-Wall', '-Wextra', '-Wno-unused-parameter', '-I.']
passed = 0
def run(label, cmd):
    global passed
    print('\n' + label, flush=True)
    subprocess.run([str(x) for x in cmd], cwd=STUB, env=env, check=True)
    passed += 1

run('MJPEG syntax', [*flags, '-fsyntax-only', 'main.cpp'])
hidden = []
try:
    for name in ('esp_camera.h', 'img_converters.h'):
        src = STUB / name
        dst = STUB / ('.check_host_' + name)
        if dst.exists():
            raise RuntimeError('Unexpected leftover check file: ' + str(dst))
        src.rename(dst)
        hidden.append((src, dst))
    run('Fallback syntax', [*flags, '-fsyntax-only', 'main.cpp'])
finally:
    for src, dst in reversed(hidden):
        dst.rename(src)
run('Voice char mode syntax', [*flags, '-DVOICE_MODE=2', '-fsyntax-only', 'main.cpp'])
with tempfile.TemporaryDirectory(prefix='stylecam_bridge_') as tmp:
    for name in ('voice_test', 'bridge_test'):
        exe = Path(tmp) / (name + '.exe')
        subprocess.run([*flags, name + '.cpp', 'shim.cpp', '-o', str(exe)], cwd=STUB, env=env, check=True)
        run(name, [exe])
run('Independent wire protocol reference', [sys.executable, HERE / 'test_frame_parser.py'])
print('\n%d/6 host checks PASS' % passed)
