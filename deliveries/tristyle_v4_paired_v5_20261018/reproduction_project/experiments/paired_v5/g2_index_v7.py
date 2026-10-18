"""Index existing real student outputs and unscaled crops; no model execution."""
from pathlib import Path
import hashlib
import html
import json
import os
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT/'reports/paired_v5'
SOURCE = REPORT/'P1b/claude_p4_vangogh_v7/006000/fixed17'
STYLES = ('vangogh', 'ukiyoe', 'ink')


def main():
    manifest = json.loads((ROOT/'data/fixed_test_manifest.json').read_text())
    out = REPORT/'P4/g2_selected_v7_v2'
    out.mkdir(exist_ok=False)
    blocks = ['<!doctype html><meta charset="utf-8"><title>G2 selected V7 actual network outputs</title>',
              '<style>body{font:16px sans-serif;margin:24px;background:#eee}figure{margin:6px}img{max-width:100%}.grid{display:grid;grid-template-columns:repeat(4,1fr)}section{background:white;padding:12px;margin-bottom:24px}strong{color:#a21c18}</style>',
              '<h1>G2: V3 vs selected candidate (VG v7, UK r2, ink r2)</h1>',
              '<p><strong>Artistic gate FAIL; provisional selection only. No teacher target in this index.</strong> Actual saved network outputs, images link to their original PNGs. Reduced mode is 320x240 internal with bilinear2x display, not native VGA and not measured FPGA FPS.</p>',
              '<p><a href="../../P3/G2_REVIEW.md">G2 review</a> · <a href="../../P3/VIDEO_RATIO_BOTH_MODES.json">Video metrics</a></p>']
    evidence = []
    for mode in ['native', 'internal320x240_2x_REDUCED_RESOLUTION']:
        blocks.append('<h2>'+html.escape(mode)+'</h2>')
        crop_dir = out/mode
        crop_dir.mkdir()
        for name in manifest:
            stem = Path(name).stem
            blocks.append('<section><h3>'+html.escape(name)+'</h3><div class="grid">')
            cells = []
            for version in [1, 2]:
                src = [SOURCE/mode/'ink'/f'{stem}_0.png'] + [SOURCE/mode/s/f'{stem}_{version}.png' for s in STYLES]
                for label, p in zip(['INPUT']+[('V3' if version==1 else 'STUDENT')+' '+s for s in STYLES], src):
                    assert p.exists(), str(p)
                    rel = os.path.relpath(p,out).replace('\\','/')
                    blocks.append(f'<figure><a href="{rel}"><img loading="lazy" src="{rel}"></a><figcaption>{label}</figcaption></figure>')
                    im = Image.open(p).convert('RGB')
                    transformed = False
                    # Reduced mode outputs are stretched to 640x480 even for
                    # non-4:3 inputs. Align the input reference to that display
                    # geometry, and do not label this reference an unscaled crop.
                    if version in [1,2] and p.name.endswith('_0.png') and mode != 'native':
                        im = im.resize((640,480),Image.Resampling.BILINEAR)
                        label = 'INPUT resized display'
                        transformed = True
                    # Network output crops retain one source output pixel per pixel.
                    cx, cy = im.width//2, im.height//2
                    if stem.startswith('sky'): cy = im.height//3
                    if stem.startswith('water'): cy = 2*im.height//3
                    left=max(0,min(im.width-256,cx-128));top=max(0,min(im.height-256,cy-128))
                    box=(left,top,min(im.width,left+256),min(im.height,top+256))
                    cells.append((label,im.crop(box),box))
                    evidence.append({'mode':mode,'scene':name,'label':label,'source':str(p.relative_to(ROOT)),
                                     'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'crop_box':box,
                                     'input_reference_resized':transformed})
            sheet=Image.new('RGB',(1024,560),'white');draw=ImageDraw.Draw(sheet)
            for i,(label,im,box) in enumerate(cells):
                x=(i%4)*256;y=(i//4)*280;sheet.paste(im,(x,y));draw.text((x+2,y+258),label+('' if 'resized' in label else ' 1:1'),fill='black')
            dest=crop_dir/f'{stem}_crop.png';sheet.save(dest)
            rel=dest.relative_to(out).as_posix()
            blocks.append(f'</div><details><summary>Unscaled diagnostic crop: source pixel=display pixel in file; same coordinates within mode</summary><a href="{rel}"><img src="{rel}" loading="lazy"></a></details></section>')
    checkpoint=ROOT/'experiments/paired_v5/claude_p4_vangogh_v7/step_006000.pt'
    (out/'MANIFEST.json').write_text(json.dumps({'checkpoint':str(checkpoint.relative_to(ROOT)),
        'checkpoint_sha256':hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
        'scope':'Existing actual student outputs only; no inference/training, no teacher',
        'gate':'FAIL', 'rows':evidence},indent=2),encoding='utf-8')
    (out/'INDEX.html').write_text('\n'.join(blocks),encoding='utf-8')
    (out/'source.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps({'output':str(out),'scenes':len(manifest),'modes':2,'crops':34,'evidence_images':len(evidence)}))


if __name__ == '__main__': main()
