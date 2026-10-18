"""CPU teacher-only component diagnosis; keeps v6 construction and subjects."""
import argparse,copy,inspect,json
from pathlib import Path
import cv2,numpy as np
from PIL import Image,ImageDraw
import claude_targets_v6 as b

def main(folder):
    folder.mkdir(parents=True,exist_ok=False);(folder/'native').mkdir()
    A=json.loads((b.ROOT/'reports/paired_v5/P1/claude_targets_v6_04/teacher_assets.json').read_text())
    original=inspect.getsource(b.ink)
    variants={}
    variants['V6']=original
    variants['NO_NORMALIZED_GRAIN']=original.replace("c['cun_strength']","0.").replace("c['paper_grain']","0.")
    variants['NO_BUSY_GREY_FLOOR']=variants['NO_NORMALIZED_GRAIN'].replace('wash = unit(np.maximum(wash, blur(busy2, 4) * .30))','wash = wash')
    variants['SPARSE_STRUCTURAL']=variants['NO_BUSY_GREY_FLOOR'].replace('bold = bold * (1 - .6 * busy2)','bold = bold * (1 - .92 * busy2)').replace("fine = l1 * np.where(busy, 0., c['fine_line_weight'] + .55 * face)","fine = l1 * np.where(busy, 0., .16 + .55 * face)")
    rows=b.preview_rows(folder)
    for name,source in variants.items(): (folder/(name+'.py')).write_text(source)
    funcs={}
    for name,source in variants.items():
        namespace=dict(vars(b));exec(source,namespace);funcs[name]=namespace['ink']
    metrics=[]
    for off in range(0,len(rows),3):
        sub=rows[off:off+3];sheet=Image.new('RGB',(1600,262*len(sub)),'white');draw=ImageDraw.Draw(sheet)
        for ri,(name,p,m) in enumerate(sub):
            a,s=b.load(p,m); images=[('INPUT',a)]
            for tag,fun in funcs.items():
                y=fun(a,s,A)[0];assert np.isfinite(y).all();images.append((tag,y))
                Image.fromarray((y*255).round().astype('uint8')).save(folder/'native'/f'{name}_{tag}.png')
                metrics.append({'scene':name,'variant':tag,'paper_fraction_luma_gt_09':float((b.gray(y)>.9).mean())})
            for col,(tag,y) in enumerate(images):
                im=Image.fromarray((y*255).round().astype('uint8'));im.thumbnail((320,240));sheet.paste(im,(col*320,ri*262));draw.text((col*320+2,ri*262+243),name+' '+tag,fill='black')
        sheet.save(folder/f'contact_{off//3+1}.jpg',quality=94)
    (folder/'manifest.json').write_text(json.dumps({'source_sha256':b.sha(__file__),'parent_sha256':b.sha(b.__file__),'teacher_only':True,'fixed17_used':False,'rows':metrics},indent=2))
    (folder/Path(__file__).name).write_bytes(Path(__file__).read_bytes())

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--out',required=True);args=a.parse_args();cv2.setNumThreads(2);main(b.ROOT/args.out)
