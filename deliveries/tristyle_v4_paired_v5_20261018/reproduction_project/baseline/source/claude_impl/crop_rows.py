"""Extract selected scene rows from a progress comparison.jpg for quick inspection."""
import sys
from PIL import Image
src, dst, rows = sys.argv[1], sys.argv[2], [int(r) for r in sys.argv[3].split(',')]
im = Image.open(src); W = im.width; rh = 256
out = Image.new('RGB', (W, rh * len(rows)))
for i, r in enumerate(rows): out.paste(im.crop((0, r * rh, W, (r + 1) * rh)), (0, i * rh))
out.save(dst, quality=90)
