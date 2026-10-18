"""Project-local pinned ffmpeg wheel extraction and H264 playback copy; no global install."""
import argparse, hashlib, json, pathlib, subprocess, zipfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser(); ap.add_argument('video'); a=ap.parse_args()
wheel=ROOT/'external_runtime/imageio_ffmpeg-0.6.0-py3-none-win_amd64.whl'
out=ROOT/'external_runtime/imageio_ffmpeg_0_6_0'; out.mkdir(exist_ok=True)
with zipfile.ZipFile(wheel) as z:
    for p in z.namelist():
        if p.endswith('.exe') or 'LICENSE' in p.upper(): z.extract(p,out)
exe=next(out.rglob('*.exe')); src=(ROOT/a.video).resolve(); dst=src.with_name(src.stem+'_h264.mp4')
cmd=[str(exe),'-hide_banner','-loglevel','error','-y','-i',str(src),'-c:v','libx264','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart','-an',str(dst)]
subprocess.run(cmd,check=True)
report={'source':str(src.relative_to(ROOT)),'source_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),
    'output':str(dst.relative_to(ROOT)),'output_sha256':hashlib.sha256(dst.read_bytes()).hexdigest(),
    'runtime_wheel':wheel.name,'wheel_sha256':hashlib.sha256(wheel.read_bytes()).hexdigest(),
    'command':cmd,'note':'Playback encoding only; no model inference, art enhancement or FPGA performance measurement.'}
dst.with_suffix('.provenance.json').write_text(json.dumps(report,indent=2)); print(json.dumps(report,indent=2))
