"""Inspect an actual UART RAW sample locally; this is not an HDMI screenshot."""
from pathlib import Path
import sys,json,argparse
import numpy as np
import cv2
from PIL import Image,ImageDraw
parser=argparse.ArgumentParser()
parser.add_argument('run',type=Path)
parser.add_argument('--black-level',type=int,default=0,help='RAW8 offset used only in the host display preview')
parser.add_argument('--kind',choices=['ROI1','RAW1'],help='Select a capture from a dual-capture run')
args=parser.parse_args();run=args.run
assert 0<=args.black_level<=255
metadata=run/'raw_capture.json'
capture=json.loads(metadata.read_text()) if metadata.exists() else {
    'kind':'RAW1','file':'thumbnail_bggr_128x72.raw','stride':15,'x0':0,'y0':0}
if args.kind:
    captures=json.loads((run/'raw_captures.json').read_text()) if (run/'raw_captures.json').exists() else [capture]
    capture=next(c for c in captures if c['kind']==args.kind)
prefix='overview_' if args.kind=='RAW1' else ''
raw=np.frombuffer((run/capture['file']).read_bytes(),dtype=np.uint8).reshape(72,128)
# Verify OpenCV's explicit Bayer order convention before interpreting color.
pattern=np.empty((8,8),dtype=np.uint8)
pattern[0::2,0::2]=40;pattern[0::2,1::2]=100;pattern[1::2,0::2]=100;pattern[1::2,1::2]=200
assert tuple(cv2.cvtColor(pattern,cv2.COLOR_BayerBGGR2RGB)[3,3])==(200,100,40)
preview_raw=np.maximum(raw.astype(np.int16)-args.black_level,0).astype(np.uint8)
rgb=cv2.cvtColor(preview_raw,cv2.COLOR_BayerBGGR2RGB)
lut=np.array([round(1023*((x*4+x//64)/1023)**(1/2.2))//4 for x in range(256)],dtype=np.uint8)
display=lut[rgb]
Image.fromarray(raw).save(run/(prefix+'raw_mosaic.png'))
Image.fromarray(display).save(run/(prefix+'raw_thumbnail_gamma_preview.png'))
canvas=Image.new('RGB',(1024,326),'#202020');draw=ImageDraw.Draw(canvas)
for i,(im,label) in enumerate([(rgb,f'RAW sample minus {args.black_level}, linear'),(display,f'RAW minus {args.black_level}, host gamma 2.2')]):
    canvas.paste(Image.fromarray(im).resize((512,288),Image.Resampling.NEAREST),(i*512,30))
    draw.text((i*512+8,8),label,fill='white')
canvas.save(run/(prefix+'raw_comparison.png'))
stats={'source':f"actual FPGA RAW8 over UART; origin ({capture['x0']},{capture['y0']}), stride {capture['stride']}; no spatial averaging",
       'capture':capture,
       'preview':'host bilinear Bayer reconstruction, NOT an HDMI screenshot; ROI1 is contiguous, RAW1 is spatially subsampled',
       'raw_percentiles':{str(q):float(np.percentile(raw,q)) for q in [0,1,5,25,50,75,95,99,100]},
       'raw_histogram':np.bincount(raw.ravel(),minlength=256).tolist(),
       'channel_means':{n:float(a.mean()) for n,a in [('B',raw[::2,::2]),('Gb',raw[::2,1::2]),('Gr',raw[1::2,::2]),('R',raw[1::2,1::2])]},
       'preview_black_level_8bit':args.black_level,
       'calibration_note':'Preview offset is an explicit argument; see black_level_calibration.json for measurement evidence.'}
(run/(prefix+'thumbnail_analysis.json')).write_text(json.dumps(stats,indent=2))
print(json.dumps({k:v for k,v in stats.items() if k!='raw_histogram'},indent=2))
