"""Place the RAW overview and 1:1 source ROI side by side for local inspection."""
from pathlib import Path
import json
import sys
from PIL import Image, ImageDraw

run = Path(sys.argv[1])
captures = {c['kind']: c for c in json.loads((run/'raw_captures.json').read_text())}
roi, overview = captures['ROI1'], captures['RAW1']
roi_stats = json.loads((run/'thumbnail_analysis.json').read_text())
overview_stats = json.loads((run/'overview_thumbnail_analysis.json').read_text())
assert roi_stats['capture'] == roi and overview_stats['capture'] == overview
black = roi_stats['preview_black_level_8bit']
assert black == overview_stats['preview_black_level_8bit']
canvas = Image.new('RGB', (1024, 348), '#18202a')
draw = ImageDraw.Draw(canvas)
for i, name in enumerate(['overview_raw_thumbnail_gamma_preview.png', 'raw_thumbnail_gamma_preview.png']):
    with Image.open(run/name) as im:
        canvas.paste(im.resize((512, 288), Image.Resampling.NEAREST), (i*512, 30))
sx = 512/(overview['width']*overview['stride'])
sy = 288/(overview['height']*overview['stride'])
x, y = (roi['x0']-overview['x0'])*sx, 30+(roi['y0']-overview['y0'])*sy
draw.rectangle((x, y, x+roi['width']*sx, y+roi['height']*sy), outline='#00ffff', width=2)
draw.text((10, 9), 'Full-scene overview (stride 15); cyan box = ROI', fill='white')
draw.text((522, 9), f"Contiguous RAW ROI ({roi['x0']},{roi['y0']}), 128x72, shown 4x", fill='white')
draw.text((10, 329), f'Actual sensor RAW8. Host BLC={black} + bilinear Bayer + gamma. Not an HDMI screenshot.', fill='#d2d8e0')
canvas.save(run/'capture_context.png')
print(run/'capture_context.png')
