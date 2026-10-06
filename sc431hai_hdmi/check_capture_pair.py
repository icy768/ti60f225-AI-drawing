"""Compare overlapping sensor coordinates in the overview and contiguous ROI."""
from pathlib import Path
import json
import sys

run = Path(sys.argv[1])
captures = {c['kind']: c for c in json.loads((run/'raw_captures.json').read_text())}
overview, roi = captures['RAW1'], captures['ROI1']
assert roi['stride'] == 1
a, b = (run/overview['file']).read_bytes(), (run/roi['file']).read_bytes()
assert len(a) == overview['width']*overview['height']
assert len(b) == roi['width']*roi['height']
checked, mismatches = 0, []
for y in range(overview['height']):
    sy = overview['y0'] + y*overview['stride']
    for x in range(overview['width']):
        sx = overview['x0'] + x*overview['stride']
        if roi['x0'] <= sx < roi['x0']+roi['width'] and roi['y0'] <= sy < roi['y0']+roi['height']:
            av = a[y*overview['width']+x]
            bv = b[(sy-roi['y0'])*roi['width']+sx-roi['x0']]
            checked += 1
            if av != bv:
                mismatches.append({'x': sx, 'y': sy, 'overview': av, 'roi': bv})
report = {'checked_shared_sensor_coordinates': checked, 'mismatches': mismatches,
          'passed': checked > 0 and not mismatches,
          'limits': 'Exact RAW8 sample/coordinate comparison only; not focus or HDMI validation.'}
(run/'capture_pair_check.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
assert report['passed']
