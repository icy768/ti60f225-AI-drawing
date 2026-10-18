"""Last time-boxed P4 teacher: content-seeded directional dry/wet pigment marks.

No painting patches, layouts, objects, coordinate noise or globally ranked
components are transferred. Local maxima are computed in a fixed 9x9 window.
"""
from pathlib import Path
import argparse,json
import cv2,numpy as np
import claude_targets_v6 as b
import ink_targets_v9_02 as wash
import ink_preview_helper as helper
VERSION='ink_targets_v10_01'
ROOT=b.ROOT
P={'version':VERSION,'seed_window':9,'seed_threshold':.014,'mark_length':7,
   'mark_width_sigma':.9,'pigment_alpha':.62,'diffusion_iterations':10,
   'diffusion_dt':.12,'dry_break_strength':.5,
   'paper':[.974,.960,.930],'ink':[.055,.065,.075],
   'source':'bounded input bandpass local maxima and structure tensor; no coordinates or artwork layouts'}

def ink(a,subject,A):
    g=b.gray(a);base=wash.ink(a,subject,A)
    paper=np.array(P['paper'],np.float32);sumi=np.array(P['ink'],np.float32)
    # The broad field comes from a separately preserved local-mass renderer.
    density=b.unit((paper[0]-base[...,0])/(paper[0]-sumi[0]))
    face=b.face_mask(a,subject)
    tx,ty,coh,en=b.tensor(b.blur(g,.8),3.5)
    band=b.blur(g,1)-b.blur(g,3)
    feature=np.maximum(-band,0)
    localmax=cv2.dilate(feature,np.ones((P['seed_window'],P['seed_window']),np.uint8))
    seeds=((feature>=localmax-1e-7)&(feature>P['seed_threshold'])).astype(np.float32)
    seeds*=b.unit((density-.08)/.28)*(1-.9*face)
    seeds*=b.unit((en-.004)/.025)
    # Advect each input-derived seed into a tapered short mark along the local
    # tangent. Max composition prevents dense texture accumulating into rings.
    h,w=g.shape;yy,xx=np.mgrid[:h,:w].astype(np.float32);marks=seeds.copy()
    for direction in (-1,1):
        px,py=xx.copy(),yy.copy();vx,vy=tx.copy(),ty.copy()
        for j in range(1,P['mark_length']+1):
            nx=cv2.remap(tx,px,py,cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT_101)
            ny=cv2.remap(ty,px,py,cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT_101)
            sign=np.where(nx*vx+ny*vy>=0,1.,-1.).astype(np.float32);vx,vy=nx*sign,ny*sign
            px+=direction*vx;py+=direction*vy
            mark=cv2.remap(seeds,px,py,cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT_101)
            marks=np.maximum(marks,mark*(1-j/(P['mark_length']+1)))
    marks=b.unit(b.blur(marks,P['mark_width_sigma'])*3.7)
    dry=b.unit(.5+(b.blur(g,.65)-b.blur(g,1.5))/.055)
    marks*=1-P['dry_break_strength']*(1-dry)
    # Spatially varying bounded capillary diffusion: the pigment deposit and
    # paper absorption differ locally; this is not a full-frame blur.
    wet=marks.copy();conductivity=.35+.65*b.unit(np.abs(band)/.035)
    for _ in range(P['diffusion_iterations']):
        p=np.pad(wet,1,mode='reflect')
        lap=p[:-2,1:-1]+p[2:,1:-1]+p[1:-1,:-2]+p[1:-1,2:]-4*wet
        wet=b.unit(wet+P['diffusion_dt']*conductivity*lap)
    pigment=b.unit(.70*marks+.30*wet)*P['pigment_alpha']
    density=b.unit(1-(1-density)*(1-pigment))
    return b.unit(paper*(1-density[...,None])+sumi*density[...,None])

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--preview',required=True);a=ap.parse_args();cv2.setNumThreads(2)
    helper.ink=ink;helper.P=P;helper.VERSION=VERSION;helper.preview(ROOT/a.preview)
    out=ROOT/a.preview
    for source in (Path(__file__),Path(wash.__file__),Path(helper.__file__)):(out/source.name).write_bytes(source.read_bytes())
    m=json.loads((out/'preview_manifest.json').read_text());m['algorithm_sha256']=b.sha(__file__)
    m['wash_source_sha256']=b.sha(wash.__file__);m['preview_helper_sha256']=b.sha(helper.__file__)
    (out/'preview_manifest.json').write_text(json.dumps(m,indent=2))
