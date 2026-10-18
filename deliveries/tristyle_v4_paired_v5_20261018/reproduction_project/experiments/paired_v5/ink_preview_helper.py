"""P4 input-local ink teacher: broad wash first, sparse structural dry lines.

Only validation / authorized Sintel <=624 previews tune this teacher. This is
an offline target, never deployment postprocessing or a student output.
"""
from pathlib import Path
import argparse, json, time
import cv2
import numpy as np
from PIL import Image, ImageDraw
import claude_targets_v6 as parent

ROOT=parent.ROOT
VERSION='ink_targets_v8_02'
P={'version':VERSION,'pre_bilateral':[9,.075,4], 'pre_passes':2,
   'wash_levels':[0.,.18,.43,.75], 'wash_sigma':.075, 'wash_mix':.80,
   'line_sigma':2.4,'line_eps':.022,'line_alpha':.72,
   'dry_break':.28,'cun_alpha':.045,'paper_grain':.0015,
   'paper':[.974,.959,.925],'ink':[.075,.085,.095],
   'source':'frozen v6 assets + input-local processing; no per-image statistics'}

def ink(a,subject,A):
    g=parent.gray(a); sm=g.copy()
    d,sc,ss=P['pre_bilateral']
    for _ in range(P['pre_passes']): sm=cv2.bilateralFilter(sm,d,sc,ss)
    # Group texture BEFORE tone quantization. Do not outline each original leaf,
    # water highlight, or snow speck and do not normalize high-frequency noise.
    tone=np.interp(sm,A['source_luma_quantiles'],A['ink_quantiles']).astype(np.float32)
    density=parent.unit((1-tone-.035)/.94)
    levels=np.array(P['wash_levels'],np.float32)
    weights=np.exp(-((density[...,None]-levels)/P['wash_sigma'])**2/2)
    grouped=(weights*levels).sum(-1)/(weights.sum(-1)+1e-6)
    wash=parent.blur(grouped,.8)*P['wash_mix']+density*(1-P['wash_mix'])
    coarse=parent.blur(sm,3)
    variance=np.maximum(parent.blur(coarse*coarse,6)-parent.blur(coarse,6)**2,0)
    blank=parent.unit((coarse-.57)/.28)*parent.unit(1-variance/.008)
    wash*=1-.95*blank
    # A local contrast proxy only; this is not measured depth or a depth map.
    near=np.sqrt(variance)
    wash*=.72+.28*parent.unit(near/.075)
    tx,ty,coherence,energy=parent.tensor(sm,4)
    face=parent.face_mask(a,subject)
    dog=parent.xdog(sm,P['line_sigma'],1.6,P['line_eps'])
    structure=parent.unit((energy-.006)/.025)
    line=dog*structure*(.3+.7*coherence)
    # Strong, sparse strokes; smooth gating avoids threshold pinholes.
    line=parent.unit((line-.13)/.65)
    line=parent.blur(line,.65)*P['line_alpha']
    # Important small contours survive at more than one scale. Dense fine
    # texture is suppressed separately instead of smoothing every subject.
    gf=parent.blur(g,.75)
    small=parent.xdog(gf,1.0,1.6,.014)
    tf,uf,cf,ef=parent.tensor(gf,2.5)
    crowded=parent.blur((small>.30).astype(np.float32),5)
    persistent=parent.unit((cf-.22)/.55)*parent.unit((ef-.007)/.025)
    sparse=parent.unit((.42-crowded)/.23)
    fine=small*persistent*sparse*(.48+.40*face)
    line=np.maximum(line,fine)
    band=parent.blur(g,1.4)-parent.blur(g,3.2)
    dry=parent.unit(.5+band/.055)
    line*=1-P['dry_break']*(1-dry)
    wet=parent.blur(line,1.7)*.18
    # Sparse short rubbing in organized regions, no normalized fine etching.
    cun=parent.lic(parent.unit(-band/.10),tx,ty,4)
    cun*=P['cun_alpha']*coherence*structure*(1-blank)*(1-face)
    wash*=1-.25*face
    density=parent.unit(1-(1-wash)*(1-line)*(1-wet)*(1-cun))
    paper=np.array(P['paper'],np.float32); dark=np.array(P['ink'],np.float32)
    out=paper*(1-density[...,None])+dark*density[...,None]
    grain=np.clip(band/.10,-1,1)*P['paper_grain']*(1-density)
    return parent.unit(out+grain[...,None])

def preview(folder):
    folder.mkdir(parents=True,exist_ok=False); (folder/'native').mkdir()
    assets=json.loads((ROOT/'reports/paired_v5/P1/claude_targets_v6_04/teacher_assets.json').read_text())
    rows=parent.preview_rows(folder); checks=[]
    for off in range(0,len(rows),3):
        sheet=Image.new('RGB',(960,262*len(rows[off:off+3])),'white');draw=ImageDraw.Draw(sheet)
        for ri,(name,path,mask) in enumerate(rows[off:off+3]):
            a,subject=parent.load(path,mask); y=ink(a,subject,assets)
            assert np.isfinite(y).all() and y.shape==a.shape
            assert np.array_equal(y,ink(a,subject,assets))
            old=parent.ink(a,subject,assets)[0]
            Image.fromarray((y*255).round().astype('uint8')).save(folder/'native'/f'{name}_ink.png')
            for col,(v,label) in enumerate(((a,'INPUT'),(old,'V6 OFFLINE TEACHER'),(y,VERSION+' OFFLINE TEACHER'))):
                im=Image.fromarray((v*255).round().astype('uint8'));im.thumbnail((320,240))
                sheet.paste(im,(col*320,ri*262));draw.text((col*320+2,ri*262+243),name+' '+label,fill='black')
        sheet.save(folder/f'contact_{off//3+1}.jpg',quality=94)
    for idx in (0,2,3):
        name,path,mask=rows[idx];a,s=parent.load(path,mask);h,w=a.shape[:2];t,l=(h-256)//2,(w-256)//2
        full=ink(a,s,assets)[t:t+256,l:l+256]
        crop=ink(a[t:t+256,l:l+256],s[t:t+256,l:l+256],assets)
        checks.append({'scene':name,'central192_MAE':float(np.abs(full-crop)[32:-32,32:-32].mean())})
    (folder/'params.json').write_text(json.dumps(P,indent=2))
    (folder/'teacher_assets.json').write_text(json.dumps(assets,indent=2))
    for p in (Path(__file__),Path(parent.__file__)): (folder/p.name).write_bytes(p.read_bytes())
    meta={'version':VERSION,'all_images_are_teacher':True,'fixed17_used':False,'heldout_video_used':False,
          'locality':checks,'locality_mean':float(np.mean([x['central192_MAE'] for x in checks])),
          'source_sha256':parent.sha(__file__),'parent_sha256':parent.sha(parent.__file__),
          'assets_sha256':parent.sha(folder/'teacher_assets.json'),
          'rows':[{'name':n,'input':str(p),'input_sha256':parent.sha(p)} for n,p,_ in rows]}
    (folder/'preview_manifest.json').write_text(json.dumps(meta,indent=2));print(json.dumps(meta['locality']))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--preview',required=True);a=ap.parse_args()
    cv2.setNumThreads(2);preview(ROOT/a.preview)
