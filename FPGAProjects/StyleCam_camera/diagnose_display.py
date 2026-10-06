"""Read-only sampling of HDMI underflow without stopping on the first event."""
import datetime, json, time
from pathlib import Path
from camera_monitor import snapshot
from hdmi_test import DisplayBoard
ROOT = Path(__file__).resolve().parent
b = DisplayBoard('COM19')
samples = []
try:
    end = time.monotonic() + 30
    while time.monotonic() < end:
        s = snapshot(b)
        samples.append(s)
        if s['display']['underflow_pixels']:
            print('UNDERFLOW', s['display'], 'style', s['style'], flush=True)
        time.sleep(.05)
finally:
    b.s.close()
    b.log.close()
    path = ROOT/'results'/f'display_diagnosis_{datetime.datetime.now():%Y%m%d_%H%M%S}.json'
    path.write_text(json.dumps(samples, indent=2), encoding='utf-8')
    print('Samples', len(samples), 'nonzero', sum(bool(s['display']['underflow_pixels']) for s in samples), 'max', max(s['display']['underflow_pixels'] for s in samples), 'report', path, flush=True)
