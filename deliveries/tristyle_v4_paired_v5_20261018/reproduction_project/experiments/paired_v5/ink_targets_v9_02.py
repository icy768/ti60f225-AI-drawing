"""P4 local connected-wash ink teacher; offline targets only."""
from pathlib import Path
import argparse, json
import cv2
import numpy as np
import ink_preview_helper as preview_helper
import claude_targets_v6 as b

VERSION='ink_targets_v9_02'
P={'version':VERSION,'morph_ellipse':[9,5],'density_power':.85,
   'wash_levels':[0.,.25,.52,.83],'level_sigma':.085,
   'line_alpha':.95,'line_sigma':1.6,'line_epsilon':.023,
   'dry_break':.48,'paper':[.974,.960,.930],'ink':[.055,.065,.075],
   'mechanism':'local connected ink masses then sparse structural strokes; no fine normalized grain'}
ROOT=b.ROOT

def ink(a,subject,A):
    g=b.gray(a)
    flat=cv2.bilateralFilter(g,9,.085,4)
    flat=cv2.bilateralFilter(flat,9,.085,4)
    tone=np.interp(flat,A['source_luma_quantiles'],A['ink_quantiles']).astype(np.float32)
    den=b.unit(1-tone)**P['density_power']
    # Local grayscale morphology joins dark pigment masses and removes fine
    # pepper marks. There is no global component sorting or global merging.
    kclose=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(9,9))
    kopen=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(5,5))
    mass=cv2.morphologyEx(den,cv2.MORPH_CLOSE,kclose,borderType=cv2.BORDER_REFLECT_101)
    mass=cv2.morphologyEx(mass,cv2.MORPH_OPEN,kopen,borderType=cv2.BORDER_REFLECT_101)
    mass=b.blur(mass,1.0)
    lv=np.array(P['wash_levels'],np.float32)
    w=np.exp(-.5*((mass[...,None]-lv)/P['level_sigma'])**2)
    q=(w*lv).sum(-1)/(w.sum(-1)+1e-6)
    wash=.65*q+.35*mass
    variance=np.maximum(b.blur(flat*flat,6)-b.blur(flat,6)**2,0)
    blank=b.unit((flat-.56)/.30)*b.unit(1-variance/.009)
    wash*=1-.9*blank
    face=b.face_mask(a,subject)
    # Sparse high-contrast contours, selecting the darker side instead of
    # surrounding every grain with a closed double ring.
    gs=b.blur(g,.8);tx,ty,coh,en=b.tensor(gs,3)
    dog=b.xdog(gs,P['line_sigma'],1.6,P['line_epsilon'])
    density=b.blur((dog>.35).astype(np.float32),6)
    sparse=b.unit((.42-density)/.24)
    structure=b.unit((en-.006)/.020)*(.3+.7*coh)
    side=b.unit(.5+(b.blur(gs,5)-gs)/.07)
    line=dog*structure*sparse*side
    line=b.unit((line-.08)/.72)*P['line_alpha']
    # Short input-following dry gaps and irregular mass boundaries are bounded,
    # rather than local RMS-normalized noise over the entire image.
    band=b.blur(g,1.3)-b.blur(g,3.2)
    marks=b.lic(np.clip(band/.07,-1,1),tx,ty,5)
    dry=b.unit(.5+marks)
    line*=1-P['dry_break']*(1-dry)
    line=b.blur(line,.45)
    wet=b.blur(line,1.8)*.19
    rubbing=b.unit(marks)*b.unit(wash/.45)*(1-face)*(1-blank)*.11
    wash*=1-rubbing
    # Face anatomy is protected by the paired content-specific edge field,
    # not a photograph reconstruction loss or copying a painting layout.
    fine=b.xdog(gs,.9,1.6,.015)*face*.30
    line=np.maximum(line,fine)
    wash*=1-.18*face
    inkden=b.unit(1-(1-wash)*(1-line)*(1-wet))
    paper=np.array(P['paper'],np.float32);sumi=np.array(P['ink'],np.float32)
    return b.unit(paper*(1-inkden[...,None])+sumi*inkden[...,None])

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--preview',required=True);args=ap.parse_args()
    cv2.setNumThreads(2)
    preview_helper.ink=ink;preview_helper.P=P;preview_helper.VERSION=VERSION
    preview_helper.preview(ROOT/args.preview)
    folder=ROOT/args.preview
    (folder/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    manifest=json.loads((folder/'preview_manifest.json').read_text())
    manifest['algorithm_sha256']=b.sha(__file__)
    manifest['preview_helper_sha256']=b.sha(preview_helper.__file__)
    (folder/'preview_manifest.json').write_text(json.dumps(manifest,indent=2))
