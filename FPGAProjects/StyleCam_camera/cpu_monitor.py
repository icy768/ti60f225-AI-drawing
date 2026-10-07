"""Read-only acceptance of the RISC-V controlled system through its UART console (115200 8N1).

Captures the boot log (sensor init, per-style deployment), then status lines for --seconds and
optionally drives style/view commands to measure style-switch latency. Writes results/cpu_video_*.json.
"""
import argparse, datetime, json, re, time
from pathlib import Path
import serial

ROOT = Path(__file__).resolve().parent
STATUS = re.compile(r'\[(\d+) ms\] fps=([\d.]+) cam=([\d.]+) nn_ms=([\d.]+) style=(\d) view=(\d) ready=(\d) proc=(\d+) cap=(\d+) '
                    r'skip=(\d+) caperr=(\d+) vid_err=(\d+) uf=(\d+) hdmi_err=(\d+) irq_err=(\d+) k3=(\d+) k2=(\d+) sw_us=(\d+) sw_max_us=(\d+)')
KEYS = ['ms', 'fps', 'cam_fps', 'nn_ms', 'style', 'view', 'styles_ready', 'processed', 'captured', 'skipped', 'capture_errors',
        'video_errors', 'hdmi_underflow', 'hdmi_errors', 'irq_errors', 'key3', 'key2', 'switch_us', 'switch_max_us']


def parse(line):
    m = STATUS.search(line)
    if not m:
        return None
    v = dict(zip(KEYS, m.groups()))
    return {k: (float(x) if '.' in x else int(x)) for k, x in v.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', default='COM21')
    ap.add_argument('--seconds', type=float, default=30)
    ap.add_argument('--boot', type=float, default=0, help='also wait this long for a fresh boot log')
    ap.add_argument('--switch', action='store_true', help='cycle styles 1,2,0 via UART and measure switch latency')
    a = ap.parse_args()
    s = serial.Serial(a.port, 115200, timeout=0.2)
    log, samples, buf = [], [], b''
    t_end = time.monotonic() + a.boot + a.seconds
    t_switch = time.monotonic() + a.boot + 6
    switches = [b'1', b'2', b'0', b'v', b'v', b'v', b'w'] if a.switch else []
    while time.monotonic() < t_end:
        buf += s.read(256)
        while b'\n' in buf:
            raw, buf = buf.split(b'\n', 1)
            line = raw.decode(errors='replace').strip()
            if not line:
                continue
            log.append(line)
            print(line, flush=True)
            if line.startswith('StyleCam RISC-V control'):
                samples, log = [], [line]           # board (re)booted: keep only this run
            st = parse(line)
            if st:
                samples.append(st)
        if switches and time.monotonic() > t_switch:
            s.write(switches.pop(0))
            t_switch = time.monotonic() + 4
    s.close()
    assert samples, 'no status lines received'
    last = samples[-1]
    steady = [x for x in samples if x['fps'] > 0]
    report = dict(time=datetime.datetime.now().isoformat(), port=a.port, boot_log=[l for l in log if not STATUS.search(l)],
                  samples=samples,
                  min_fps=min(x['fps'] for x in steady) if steady else 0,
                  mean_fps=sum(x['fps'] for x in steady) / len(steady) if steady else 0,
                  sensor_fps=last['cam_fps'], nn_ms=last['nn_ms'],
                  errors=dict(capture=last['capture_errors'], video=last['video_errors'], hdmi=last['hdmi_errors'],
                              irq=last['irq_errors'], hdmi_underflow_last_frame=last['hdmi_underflow']),
                  styles_ready=last['styles_ready'], switch_max_us=last['switch_max_us'])
    first = samples[0]
    span = (last['ms'] - first['ms']) / 1000
    # stable rate = published frames / elapsed time over the whole run (per-window values are also kept)
    report['counter_fps'] = (last['processed'] - first['processed']) / span if span > 0 else 0
    report['counter_sensor_fps'] = (last['captured'] + last['skipped'] - first['captured'] - first['skipped']) / span if span > 0 else 0
    report['passed'] = (bool(steady) and round(report['counter_fps'], 2) >= 15.0 and report['min_fps'] >= 14.9
                        and not any(report['errors'].values()) and last['styles_ready'] == 7)
    out = ROOT / 'results' / f'cpu_video_{datetime.datetime.now():%Y%m%d_%H%M%S}.json'
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('counter fps', round(report['counter_fps'], 3), 'min window fps', report['min_fps'], 'errors', report['errors'],
          'switch max us', report['switch_max_us'], 'PASS' if report['passed'] else 'FAIL', out)


if __name__ == '__main__':
    main()
