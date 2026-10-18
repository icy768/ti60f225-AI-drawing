"""Deterministic input-local paired teachers. THESE ARE NOT STUDENT OUTPUTS.

P1 tuning is restricted to validation and <=624 Sintel training frames.
No coordinate noise, external layout transfer, or deployment postfilter.
"""
from pathlib import Path
import argparse
import hashlib
import heapq
import json
import sys
import time

import cv2
import numpy as np
from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parents[2]
V3=Path(json.loads((ROOT/'baseline/manifest.json').read_text())['V3_root'])
STYLES=('vangogh','ukiyoe','ink')
CONFIG={
 'version':'paired_v5_targets_12','source_noise':'input luminance highpass only; no coordinate RNG',
 'ukiyoe':{'half_meanshift_sp':8,'half_meanshift_sr':18,'initial_colors':24,'min_region_fraction':.003,'max_regions':100,'palette_blend':.58,'paper_texture':.003,'outline_strength':.63},
 'ink':{'bilateral_sigma_color':.15,'bilateral_sigma_space':7,'soft_levels':[.07,.34,.65,.96],'soft_level_sigma':.035,'soft_mix':.95,'line_strength':.28,'wet_edge_strength':.12,'dry_strength':.075,'paper_rgb':[.982,.970,.944],'organized_mass_region_weight':.82,'photographic_local_contrast_weight':.10,'protected_skin_ink_levels':[.22,.48,.72],'protected_skin_soft_sigma':.065},
 'vangogh':{'kuwahara_radius':5,'LIC_short':3,'LIC_medium':9,'LIC_long':24,'stroke_amplitude':.055,'emboss_strength':.025,'palette_blend':.16,'face_stroke_scale':.5,'fine_seed_amplitude_floor':.006,'coarse_seed_amplitude_floor':.008,'physical_mark_radii':[9,5,2.5],'mark_start':'input bandpass local extrema, no coordinate grid or RNG','max_marks_per_layer':1600,'detail_tensor_scale':.030,'detail_HP_RMS_scale':.025,'detail_tensor_weight':.35}}

CONFIG['ink'].update({'bilateral_diameter':7,'bilateral_sigma_color':.10,'bilateral_sigma_space':3,
 'hist_match_mode':'fixed12validationSourceCDF_to_realInkCDF',
 'wash_mass_weight':.95,'wash_boundary_diffusion_sigma':1.15,
 'wash_boundary_band_sigma':2.2,'wash_render':'piecewise ink mass; diffuse only near mass boundaries; no source-guided wash regression',
 'photographic_local_contrast_weight':0.})
CONFIG['vangogh']['mark_canvas_prefilter_sigma']=0.

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def blur(a,s):return cv2.GaussianBlur(a,(0,0),s,borderType=cv2.BORDER_REFLECT_101)
def gray(a):return a@np.array([.299,.587,.114],np.float32)
def norm(a,s=2.):return np.tanh(a/(np.sqrt(blur(a*a,s))+1e-4))
def unit(a):return np.clip(a,0,1).astype(np.float32)

def guided(guide,p,r=4,eps=.002):
    mean=lambda z:cv2.boxFilter(z,-1,(r*2+1,r*2+1),borderType=cv2.BORDER_REFLECT_101)
    mi,mp=mean(guide),mean(p);var=mean(guide*guide)-mi*mi;cov=mean(guide*p)-mi*mp
    aa=cov/(var+eps);bb=mp-aa*mi
    return mean(aa)*guide+mean(bb)

def field(a):
    g=blur(gray(a),1.5);gx=cv2.Sobel(g,cv2.CV_32F,1,0)/8;gy=cv2.Sobel(g,cv2.CV_32F,0,1)/8
    xx,yy,xy=blur(gx*gx,3),blur(gy*gy,3),blur(gx*gy,3)
    theta=.5*np.arctan2(2*xy,xx-yy)+np.pi/2
    return np.cos(theta).astype(np.float32),np.sin(theta).astype(np.float32),np.sqrt(xx+yy)

def lic(source,tx,ty,length):
    h,w=source.shape;yy,xx=np.mgrid[:h,:w].astype(np.float32);total=source.copy();weight=np.ones_like(source)
    for direction in (-1,1):
        px,py=xx.copy(),yy.copy();vx,vy=tx.copy(),ty.copy()
        for j in range(1,length+1):
            nx=cv2.remap(tx,px,py,cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT_101);ny=cv2.remap(ty,px,py,cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT_101)
            sign=np.where(nx*vx+ny*vy>=0,1.,-1.).astype(np.float32);vx,vy=nx*sign,ny*sign
            px+=direction*vx;py+=direction*vy;ww=1-j/(length+1)
            total+=cv2.remap(source,px,py,cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT_101)*ww;weight+=ww
    return total/weight

def face_mask(a,subject):
    # Conservative skin proxy intersected with available subject masks. This
    # is NOT a face detector; review faces explicitly at G1.
    r,g,b=a.transpose(2,0,1);skin=(r>.20)&(r>g*.95)&(g>b*.95)&(r-b>.035)&(r-g<.30)
    support=subject if subject.max()>.05 else np.ones_like(subject)*.75
    return blur(skin.astype(np.float32)*support,3).clip(0,1)

def build_assets(out):
    manifest_path=ROOT/'data/curated_references.json';manifest=json.loads(manifest_path.read_text(encoding='utf-8'));pal=[];ink=[];sources=[]
    # Membership follows PLAN's v2 exactly. Apply the later manually verified
    # exclusions too: v2 alone still contains calligraphy on reference51856.
    correction_path=ROOT/'data/curated_references_v3.json'
    corrections={r['id']:r for r in json.loads(correction_path.read_text(encoding='utf-8'))['references']}
    for r in manifest['references']:
        if not r.get('use_for_training',True) or r['style'] not in ('ukiyoe','ink'):continue
        p=ROOT/r['path'];assert sha(p)==r['sha256'];a=np.array(Image.open(p).convert('RGB'),copy=True).astype(np.float32)/255;h,w=a.shape[:2]
        valid=np.zeros((h,w),np.uint8);l,t,rr,b=r['painting_ROI_normalized'];valid[round(t*h):round(b*h),round(l*w):round(rr*w)]=1
        exclusions=r['exclusion_regions_normalized']+corrections.get(r['id'],{}).get('exclusion_regions_normalized',[])
        for l,t,rr,b in exclusions:valid[int(t*h):int(np.ceil(b*h)),int(l*w):int(np.ceil(rr*w))]=0
        # Deterministic bounded subsample, equal opportunity per reference.
        pixels=a[valid.astype(bool)];stride=max(1,len(pixels)//12000);pixels=pixels[::stride][:12000]
        if r['style']=='ukiyoe':pal.append(pixels)
        else:
            lum=gray(pixels);lo,hi=np.quantile(lum,[.01,.95]);ink.append(np.clip(.04+.94*(lum-lo)/max(.1,hi-lo),.02,.99))
        sources.append({'id':r['id'],'style':r['style'],'path':r['path'],'sha256':sha(p),'exclusions':exclusions,'samples':len(pixels)})
    cv2.setRNGSeed(20261098);z=cv2.cvtColor(np.concatenate(pal).reshape(-1,1,3),cv2.COLOR_RGB2LAB).reshape(-1,3)
    _,_,centers=cv2.kmeans(z.astype(np.float32),16,None,(cv2.TERM_CRITERIA_EPS+cv2.TERM_CRITERIA_MAX_ITER,60,.05),1,cv2.KMEANS_PP_CENTERS)
    centers=centers[np.argsort(centers[:,0])];qs=np.linspace(0,1,257);vals=np.quantile(np.concatenate(ink),qs).astype(np.float32)
    # A fixed source CDF removes per-image rank ambiguity: a small dark face
    # must not become pale because it happens to be the brightest object.
    # Calibrate ONLY on the prescribed12 validation inputs, never fixed17/video holdout.
    files=sorted((V3/'data/claude_targets/content/validation').glob('*.png'))
    ids=np.linspace(0,len(files)-1,12).round().astype(int);content_luma=[];calibration=[]
    for i in ids:
        p=files[i];rgb=np.array(Image.open(p).convert('RGB'),copy=True).astype(np.float32)/255
        valid_rows=np.flatnonzero(rgb.mean((1,2))>.008)
        if len(valid_rows):rgb=rgb[valid_rows[0]:valid_rows[-1]+1]
        lum=gray(rgb).ravel();content_luma.append(lum[::max(1,len(lum)//12000)][:12000])
        calibration.append({'path':str(p),'sha256':sha(p),'split':'validation target tuning only'})
    source_values=np.quantile(np.concatenate(content_luma),qs).astype(np.float32)
    result={'palette_lab':centers.tolist(),'ink_quantile_values':vals.tolist(),'ink_quantile_positions':qs.tolist(),'fixed_content_luma_quantiles':source_values.tolist(),'content_CDF_calibration':calibration,'hist_match_mode':'fixed validation-source CDF to real-ink CDF; no per-scene reranking','sources':sources,'manifest_sha256':sha(manifest_path),'extra_exclusions_sha256':sha(correction_path),'source_sha256':sha(__file__),'normalization':'ink per-reference .01/.95 endpoints; equal bounded reference sample count'}
    out.mkdir(parents=True,exist_ok=True);(out/'teacher_assets.json').write_text(json.dumps(result,indent=2));(out/'params.json').write_text(json.dumps(CONFIG,indent=2));(out/'source_targets_v5.py').write_bytes(Path(__file__).read_bytes());return result

def merged_regions(rgb,cfg,subject=None):
    h,w=rgb.shape[:2];small=cv2.resize((rgb*255).round().astype(np.uint8),(max(16,w//2),max(16,h//2)),interpolation=cv2.INTER_AREA)
    ms=cv2.pyrMeanShiftFiltering(small,cfg['half_meanshift_sp'],cfg['half_meanshift_sr'],maxLevel=1);lab=cv2.cvtColor(ms.astype(np.float32)/255,cv2.COLOR_RGB2LAB);flat=lab.reshape(-1,3)
    cv2.setRNGSeed(20261098);_,ids,_=cv2.kmeans(flat,cfg['initial_colors'],None,(cv2.TERM_CRITERIA_EPS+cv2.TERM_CRITERIA_MAX_ITER,30,.3),1,cv2.KMEANS_PP_CENTERS);ids=ids.reshape(lab.shape[:2]);labels=np.zeros(ids.shape,np.int32);n=0
    subject_small=cv2.resize(subject,ids.shape[::-1],interpolation=cv2.INTER_AREA) if subject is not None else np.zeros(ids.shape,np.float32)
    ids=ids+(subject_small>.3).astype(np.int32)*cfg['initial_colors']
    for color in np.unique(ids):
        count,cc=cv2.connectedComponents((ids==color).astype(np.uint8),connectivity=4);sel=cc>0;labels[sel]=cc[sel]+n-1;n+=count-1
    area=np.bincount(labels.ravel(),minlength=n).astype(np.int64);sums=np.stack([np.bincount(labels.ravel(),weights=lab[...,c].ravel(),minlength=n) for c in range(3)],1)
    subject_sum=np.bincount(labels.ravel(),weights=subject_small.ravel(),minlength=n)
    neighbors=[set() for _ in range(n)];parent=np.arange(n);active=np.ones(n,bool)
    pairs=np.concatenate((np.stack((labels[:,:-1].ravel(),labels[:,1:].ravel()),1),np.stack((labels[:-1].ravel(),labels[1:].ravel()),1)))
    for a,b in np.unique(np.sort(pairs,axis=1),axis=0):
        if a!=b:neighbors[a].add(int(b));neighbors[b].add(int(a))
    heap=[(int(area[i]),i) for i in range(n)];heapq.heapify(heap);live=n;minimum=cfg['min_region_fraction']*labels.size
    while heap:
        ar,a=heapq.heappop(heap)
        if not active[a] or ar!=area[a]:continue
        if live<=cfg['max_regions'] and (ar>=minimum or live<=40):break
        candidates=[b for b in neighbors[a] if active[b]]
        if not candidates:continue
        mean=sums[a]/area[a];b=min(candidates,key=lambda k:float(np.linalg.norm(mean-sums[k]/area[k])+70*abs(subject_sum[a]/area[a]-subject_sum[k]/area[k])))
        active[a]=False;parent[a]=b;area[b]+=area[a];sums[b]+=sums[a];subject_sum[b]+=subject_sum[a];live-=1
        nb=(neighbors[a]|neighbors[b])-{a,b};neighbors[b]=nb
        for k in nb:neighbors[k].discard(a);neighbors[k].add(b)
        heapq.heappush(heap,(int(area[b]),b))
    def root(i):
        while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
        return i
    lut=np.array([root(i) for i in range(n)]);_,merged=np.unique(lut[labels],return_inverse=True);merged=merged.reshape(labels.shape).astype(np.int32)
    return cv2.resize(merged,(w,h),interpolation=cv2.INTER_NEAREST),{'initial_regions':n,'merged_regions':live,'min_area_fraction':cfg['min_region_fraction']}

def ukiyoe(a,subject,assets):
    cfg=CONFIG['ukiyoe'];labels,stats=merged_regions(a,cfg,subject);lab=cv2.cvtColor(a,cv2.COLOR_RGB2LAB);result=np.empty_like(lab);palette=np.array(assets['palette_lab'],np.float32)
    for i in np.unique(labels):
        sel=labels==i;pixels=lab[sel];med=np.median(pixels,axis=0);weights=np.array([.7,1.,1.],np.float32);p=palette[np.argmin(np.sum(((palette-med)*weights)**2,axis=1))];color=med*(1-cfg['palette_blend'])+p*cfg['palette_blend'];result[sel]=color
        # At most two gentle luminance values per region; no photo ramp.
        threshold=np.median(pixels[:,0]);result[sel,0]+=np.where(pixels[:,0]>threshold,1.5,-1.5)
    # Significant region boundaries only; preserve long structural segments.
    bd=np.zeros(labels.shape,np.float32);d=np.linalg.norm(result[:,1:]-result[:,:-1],axis=2);bd[:,1:]=((labels[:,1:]!=labels[:,:-1])&(d>10)).astype(np.float32);d=np.linalg.norm(result[1:]-result[:-1],axis=2);bd[1:]=np.maximum(bd[1:],((labels[1:]!=labels[:-1])&(d>10)).astype(np.float32))
    count,cc,st,_=cv2.connectedComponentsWithStats((bd>0).astype(np.uint8),8);keep=np.zeros_like(bd)
    for i in range(1,count):
        if st[i,cv2.CC_STAT_AREA]>=max(16,a.shape[1]*.035):keep[cc==i]=1
    # Sparse long input structures recover thin subject parts omitted by
    # region merging. No edges from busy foliage/microtexture are admitted.
    src=gray(a);g8=(blur(src,1.5)*255).round().astype(np.uint8);major=cv2.Canny(g8,45,105)
    quiet=blur(np.abs(src-blur(src,1.0)),3)<.023;support=cv2.dilate((subject>.2).astype(np.uint8),np.ones((5,5),np.uint8))>0
    structural=((major>0)&(quiet|support)).astype(np.uint8);nc,lc,sc,_=cv2.connectedComponentsWithStats(structural,8)
    for i in range(1,nc):
        if sc[i,cv2.CC_STAT_AREA]>=max(24,a.shape[1]*.08):keep[lc==i]=np.maximum(keep[lc==i],.65)
    keep=blur(keep,.5)
    y=cv2.cvtColor(result,cv2.COLOR_LAB2RGB);lum=gray(a);hp=lum-blur(lum,2)
    h,w=lum.shape;vertical=np.linspace(0,1,h,dtype=np.float32)[:,None];sky=(a[...,2]>a[...,0]*.95)&(lum>.57)&(vertical<.55)&(subject<.1);sky=blur(sky.astype(np.float32),5)
    y+=sky[...,None]*(vertical[...,None]-.25)*np.array([.035,.045,.065],np.float32)
    paper=np.array([1.,.985,.945],np.float32);y=y*.97+paper*.03+norm(hp)[...,None]*cfg['paper_texture'];line=cv2.dilate(keep,np.ones((2,2),np.uint8))*cfg['outline_strength'];y=y*(1-line[...,None])+np.array([.07,.10,.14],np.float32)*line[...,None]
    return unit(y),stats

def ink(a,subject,assets):
    cfg=CONFIG['ink'];g=gray(a);tx,ty,energy=field(a)
    # Avoid applying Kuwahara and two broad guided passes before the face
    # structure is established. A single edge-preserving luminance smooth is
    # the histogram input; organized masses below still remove photo shading.
    smooth=cv2.bilateralFilter(g,cfg['bilateral_diameter'],cfg['bilateral_sigma_color'],cfg['bilateral_sigma_space'])
    matched=np.interp(smooth,assets['fixed_content_luma_quantiles'],assets['ink_quantile_values']).astype(np.float32)
    # Preserve dynamic organization after the real-reference CDF; no hard white
    # threshold. Local important edges guide bleed instead of being blurred out.
    # A dark scene must not turn into a white photographic negative merely
    # because its CDF rank is high. Preserve local structure with a monotone
    # partial match, retaining the original rank/tone organization.
    matched=unit(matched*.55+smooth*.45)
    # Broad organized wash masses replace within-region photographic shading;
    # retain a small continuous fraction for soft boundaries, never binary ink.
    labels,mass_stats=merged_regions(a,CONFIG['ukiyoe'],subject);mass=np.empty_like(matched)
    for i in np.unique(labels):
        sel=labels==i;mass[sel]=np.median(matched[sel])
    matched=mass*cfg['wash_mass_weight']+matched*(1-cfg['wash_mass_weight'])
    centers=np.array(cfg['soft_levels'],np.float32);weights=np.exp(-.5*((matched[...,None]-centers)/cfg['soft_level_sigma'])**2);soft=(weights*centers).sum(-1)/(weights.sum(-1)+1e-8);wash=matched*(1-cfg['soft_mix'])+soft*cfg['soft_mix']
    # Guided regression on photographic luminance recreated its gradients
    # even from flattened masses. Keep interiors flat; bleed boundary bands.
    mass_edge=cv2.magnitude(cv2.Sobel(mass,cv2.CV_32F,1,0)/8,cv2.Sobel(mass,cv2.CV_32F,0,1)/8)
    edge_band=np.clip(blur(mass_edge,cfg['wash_boundary_band_sigma'])*12,0,.8)
    wash=wash*(1-edge_band)+blur(wash,cfg['wash_boundary_diffusion_sigma'])*edge_band
    # Actual pigment diffusion: expand density into nearby lighter paper.
    # The previous absolute Laplacian darkened BOTH sides and looked embossed.
    density=unit(1-wash);diffused=blur(density,2.2)
    wet=np.maximum(diffused-density,0)*cfg['wet_edge_strength']*1.8
    wet_rim=np.maximum(density-diffused,0)*.04
    wash-=wet+wet_rim
    dog=blur(g,.8)-blur(g,1.6)*.98;line=np.maximum(np.tanh((-dog-.004)*45),0);hp=g-blur(g,2);dry=np.clip(.72+.28*norm(hp),0,1);line*=dry
    broad=cv2.magnitude(cv2.Sobel(blur(g,1.3),cv2.CV_32F,1,0)/8,cv2.Sobel(blur(g,1.3),cv2.CV_32F,0,1)/8);width=np.clip(energy/.035,0,1);line=line*(1-width)+cv2.dilate(line,np.ones((2,2),np.uint8))*width
    texture=np.maximum(blur((g-blur(g,4))**2,3)-.0008,0);texture=np.clip(texture/.008,0,1);stroke=norm(blur(lic(norm(hp),tx,ty,4),.65))
    # Asymmetric dark bristles and restrained paper breaks replace signed
    # bump-map shading. They are limited to real high-variance source regions.
    dark_brush=np.maximum(stroke-.12,0)*texture*(.35+.65*density)
    paper_break=np.maximum(-stroke-.50,0)*texture*np.clip((density-.35)*2,0,1)
    wash-=cfg['dry_strength']*dark_brush;wash+=.06*paper_break
    line*=1-.75*texture*(1-subject*.5)
    wash-=line*cfg['line_strength'];detail=blur(np.abs(hp),5);blank=np.clip((g-.70)/.25,0,1)*np.exp(-detail/.012)*(1-subject);blank=blur(blank,4);wash=wash*(1-blank*.65)+.985*blank*.65
    # Low-detail upper backgrounds may be mist, never erase protected subjects.
    vertical=np.linspace(1,0,g.shape[0],dtype=np.float32)[:,None];mist=vertical*np.exp(-detail/.01)*(1-subject)*.05;wash=wash*(1-mist)+.97*mist
    # Do not blend photographic luminance back onto faces. Keep their local
    # structure through ink marks while the same soft ink levels remain free.
    face=face_mask(a,subject)
    # Use three SOFT ink tones inside protected skin, not the globally bright
    # landscape CDF and not photographic luminance blended back unchanged.
    face_centers=np.array(cfg['protected_skin_ink_levels'],np.float32)
    face_w=np.exp(-.5*((smooth[...,None]-.02-face_centers)/cfg['protected_skin_soft_sigma'])**2)
    face_tone=(face_w*face_centers).sum(-1)/(face_w.sum(-1)+1e-8)
    wash=wash*(1-face*.85)+face_tone*(face*.85)
    # Restore only sparse important input structure, not full texture/shadow.
    form_dog=blur(g,1.1)-blur(g,2.2)*.985
    form_line=np.maximum(np.tanh((-form_dog-.004)*40),0)
    form_support=np.maximum(face,subject*.55)
    wash-=form_line*form_support*.30
    wash-=.14*face*np.maximum(blur(smooth,7)-smooth,0)
    wash=unit(wash);paper=np.array(cfg['paper_rgb'],np.float32);inkrgb=np.array([.035,.045,.055],np.float32);y=inkrgb+(paper-inkrgb)*wash[...,None]
    return unit(y),{'soft_ink_levels':4,'hist_match':'real ink ROI distribution, not per-scene art layout','face_mask':'skin proxy intersected subject; must visually review'}

def anisotropic_kuwahara(a,tx,ty,radius):
    h,w=a.shape[:2];yy,xx=np.mgrid[:h,:w].astype(np.float32);candidates=[];variances=[]
    for sx,sy in ((-1,-1),(-1,1),(1,-1),(1,1)):
        mean=np.zeros_like(a);square=np.zeros_like(a);n=0
        for i in range(0,radius+1,2):
            for j in range(0,radius+1,2):
                ox=tx*i*sx-ty*j*sy;oy=ty*i*sx+tx*j*sy;sample=cv2.remap(a,xx+ox,yy+oy,cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT_101);mean+=sample;square+=sample*sample;n+=1
        mean/=n;variance=(square/n-mean*mean).sum(-1);candidates.append(mean);variances.append(variance)
    weights=np.exp(-np.stack(variances)/.004);weights/=weights.sum(0,keepdims=True)+1e-8
    return (np.stack(candidates)*weights[...,None]).sum(0)

def pigment_marks(ref,tx,ty,detail,face,cfg):
    """Coarse-to-fine input-seeded pressure-tapered marks, not a global ripple."""
    h,w=ref.shape[:2];g=gray(ref)
    # Keep the directional Kuwahara base outside actual pigment marks.
    # A second global sigma4 blur erased details even where no mark landed.
    sigma=cfg['mark_canvas_prefilter_sigma'];canvas=(blur(ref,sigma) if sigma>0 else ref).copy();coverage=np.zeros((h,w),np.float32)
    for radius in cfg['physical_mark_radii']:
        col=blur(ref,max(.6,radius*.28));signal=np.abs(g-blur(g,max(1.,radius)))+detail*.008
        size=max(3,int(radius*1.7)//2*2+1);peaks=(signal>=cv2.dilate(signal,np.ones((size,size),np.uint8))-1e-7)&(signal>.001)
        ys,xs=np.nonzero(peaks);scores=signal[ys,xs];order=np.argsort(scores,kind='stable')
        if len(order)>cfg['max_marks_per_layer']:order=order[-cfg['max_marks_per_layer']:]
        for j in order:
            y,x=int(ys[j]),int(xs[j]);color=col[y,x].copy();steps=int(3+7*(1-float(detail[y,x])));width=max(1,round(radius*(1-.45*float(face[y,x]))*(1-.60*float(detail[y,x]))));stride=max(1.,radius*.5)
            def trace(direction):
                px,py=float(x),float(y);vx,vy=tx[y,x],ty[y,x];points=[]
                for _ in range(steps):
                    ix,iy=round(px),round(py)
                    if ix<1 or iy<1 or ix>=w-1 or iy>=h-1:break
                    nx,ny=tx[iy,ix],ty[iy,ix]
                    if nx*vx+ny*vy<0:nx,ny=-nx,-ny
                    vx,vy=.6*vx+.4*nx,.6*vy+.4*ny;length=np.hypot(vx,vy)+1e-8;vx,vy=vx/length,vy/length
                    px+=direction*vx*stride;py+=direction*vy*stride
                    if len(points)>1 and np.linalg.norm(col[iy,ix]-color)>.22:break
                    points.append([int(np.clip(round(px),0,w-1)),int(np.clip(round(py),0,h-1))])
                return points
            pts=trace(-1)[::-1]+[[x,y]]+trace(1)
            if len(pts)<3:continue
            pts=np.array(pts,np.int32);margin=width+3;l,t=np.maximum(pts.min(0)-margin,0);r,b=np.minimum(pts.max(0)+margin+1,[w,h]);mask=np.zeros((b-t,r-l),np.uint8);q=pts-[l,t]
            for k in range(1,len(q)):
                pressure=.35+.65*np.sin(np.pi*k/len(q));cv2.line(mask,tuple(q[k-1]),tuple(q[k]),255,max(1,round(width*pressure)),cv2.LINE_AA)
            compatibility=np.exp(-np.sum((ref[t:b,l:r]-color)**2,axis=2)/.012)
            alpha=mask.astype(np.float32)/255*(.88-.22*float(face[y,x]))*compatibility;roi=canvas[t:b,l:r];roi[:]=roi*(1-alpha[...,None])+color*alpha[...,None]
            # Fixed upper-left pigment relief is supported only by actual marks.
            aa=mask.astype(np.float32)/255;relief=(aa-blur(aa,1.))*.012-(cv2.Sobel(aa,cv2.CV_32F,1,0)+cv2.Sobel(aa,cv2.CV_32F,0,1))*.004
            roi[:]=unit(roi+relief[...,None]);coverage[t:b,l:r]=np.maximum(coverage[t:b,l:r],alpha)
    return canvas,coverage

def vangogh(a,subject,assets):
    cfg=CONFIG['vangogh'];tx,ty,energy=field(a);g=gray(a);texture=np.sqrt(blur((g-blur(g,1.2))**2,4))
    wt=cfg['detail_tensor_weight'];detail=unit(wt*unit(energy/cfg['detail_tensor_scale'])+(1-wt)*unit(texture/cfg['detail_HP_RMS_scale']))
    theta=.5*np.arctan2(blur(2*tx*ty,7),blur(tx*tx-ty*ty,7));tx,ty=np.cos(theta),np.sin(theta)
    base=anisotropic_kuwahara(a,tx,ty,cfg['kuwahara_radius']);g=gray(a);hp=blur(g,.65)-blur(g,2.5);coarse=blur(g,2.)-blur(g,9.)
    # Previous normalization amplified almost-flat input fluctuations into
    # equal-strength wood-grain everywhere. Seed only real local extrema and
    # retain input-derived amplitude for both fine and broad pigment layers.
    amplitude=np.sqrt(blur(hp*hp,4));coarse_amplitude=np.sqrt(blur(coarse*coarse,7))
    maxima=np.abs(hp)>=cv2.dilate(np.abs(hp),np.ones((3,3),np.uint8))-.00001
    noise=norm(hp,5)*maxima.astype(np.float32)
    short=lic(noise,tx,ty,cfg['LIC_short']);medium=lic(noise,tx,ty,cfg['LIC_medium']);long=lic(norm(coarse,7),tx,ty,cfg['LIC_long'])
    fine_gate=unit(amplitude/cfg['fine_seed_amplitude_floor']);coarse_gate=unit(coarse_amplitude/cfg['coarse_seed_amplitude_floor'])
    height=norm(blur(short*detail+medium*(1-detail),.55),5)*fine_gate*.55+norm(blur(long,1.3),7)*coarse_gate*.45
    face=face_mask(a,subject);amp=cfg['stroke_amplitude']*(1-face*(1-cfg['face_stroke_scale']));dx=cv2.Sobel(height,cv2.CV_32F,1,0)/8;dy=cv2.Sobel(height,cv2.CV_32F,0,1)/8;emboss=np.tanh((-dx-dy)*2)*cfg['emboss_strength']
    painted,coverage=pigment_marks(base,tx,ty,detail,face,cfg)
    important=unit(energy/.035)*.85
    painted=painted*(1-important[...,None])+base*important[...,None]
    y=painted*(1+height[...,None]*amp[...,None]*coverage[...,None])+emboss[...,None]*(1-face[...,None]*.5)*coverage[...,None]
    hsv=cv2.cvtColor(unit(y),cv2.COLOR_RGB2HSV);hsv[...,1]=np.clip(hsv[...,1]*1.12,0,1);y=cv2.cvtColor(hsv,cv2.COLOR_HSV2RGB)
    lum=gray(y);warm=np.array([.045,.012,-.035],np.float32);cool=np.array([-.025,.005,.045],np.float32);y+=lum[...,None]*warm+(1-lum[...,None])*cool
    # Gentle pigment direction only; stroke generation is separate above.
    pigments=np.array([[.10,.23,.58],[.94,.73,.12],[.12,.48,.32],[.74,.49,.24],[.90,.86,.68]],np.float32);flat=y.reshape(-1,3);dist=((flat[:,None]-pigments[None])**2).sum(-1);p=pigments[dist.argmin(1)].reshape(y.shape);mix=cfg['palette_blend']*(1-face*.7);y=y*(1-mix[...,None])+p*mix[...,None]
    return unit(y),{'input_derived_noise':True,'LIC_lengths':[cfg['LIC_short'],cfg['LIC_medium'],cfg['LIC_long']],'thick_paint_light':'upper left','not_student':True}

def preview(out):
    cv2.setNumThreads(2);out.mkdir(parents=True,exist_ok=True);assets=build_assets(out);files=sorted((V3/'data/claude_targets/content/validation').glob('*.png'));ids=np.linspace(0,len(files)-1,12).round().astype(int);rows=[]
    for i in ids:
        p=files[i];m=V3/'data/claude_targets/content_masks/validation'/p.name;rows.append(('validation_'+p.stem,p,m if m.exists() else None))
    # Already-defined training-pair files only; assert frame numbers <=624.
    pairs=sorted((V3/'data/video/train_pairs').glob('*.npz'));selected=[pairs[i] for i in np.linspace(0,len(pairs)-1,3).round().astype(int)]
    for i,p in enumerate(selected):
        import re
        nums=[int(v) for v in re.findall(r'\d+',p.stem)];assert nums and max(nums)<=624,(p,'not training segment')
        a=np.load(p)['a'];source=out/f'sintel_training_{i}.png';Image.fromarray(a).save(source);rows.append(('sintel_training_'+str(i),source,None))
    manifest=[];start=time.time()
    for offset in range(0,len(rows),3):
        subset=rows[offset:offset+3];sheet=Image.new('RGB',(4*320,len(subset)*262),'white');draw=ImageDraw.Draw(sheet)
        for ri,(stem,p,mp) in enumerate(subset):
            a=np.array(Image.open(p).convert('RGB'),copy=True).astype(np.float32)/255;subject=np.array(Image.open(mp).convert('L'),copy=True).astype(np.float32)/255 if mp else np.zeros(a.shape[:2],np.float32)
            images=[a];stats={};native=out/'native';native.mkdir(exist_ok=True)
            # Remove only near-exact black video letterbox rows from image
            # statistics; restore them unchanged in offline targets.
            rowlevel=a.mean((1,2));valid=np.flatnonzero(rowlevel>.008);top,bottom=(int(valid[0]),int(valid[-1])+1) if len(valid) else (0,a.shape[0]);crop=a[top:bottom];maskcrop=subject[top:bottom]
            for style,fn in zip(STYLES,(vangogh,ukiyoe,ink)):
                yc,stats[style]=fn(crop,maskcrop,assets);y=a.copy();y[top:bottom]=yc;stats[style]['active_rows']=[top,bottom];Image.fromarray((y*255).round().astype(np.uint8)).save(native/f'{stem}_{style}_TEACHER.png');images.append(y)
            for col,(label,v) in enumerate(zip(('INPUT','VANGOGH TEACHER','UKIYOE TEACHER','INK TEACHER'),images)):
                im=Image.fromarray((unit(v)*255).round().astype(np.uint8));im.thumbnail((320,240));sheet.paste(im,(col*320,ri*262));draw.text((col*320+2,ri*262+243),stem+' '+label,fill='black')
            manifest.append({'name':stem,'input':str(p),'input_sha256':sha(p),'mask':str(mp) if mp else None,'mask_sha256':sha(mp) if mp else None,'stats':stats});print('P1_TARGET',stem,stats,'seconds',time.time()-start,flush=True)
        sheet.save(out/f'contact_{offset//3+1}.jpg',quality=95)
    (out/'preview_manifest.json').write_text(json.dumps({'source_sha256':sha(__file__),'fixed17_used':False,'heldout_video_used':False,'all_images_are_teacher':True,'Sintel_training_pair_files':[{'path':str(p),'sha256':sha(p)} for p in selected],'rows':manifest},indent=2))
    (out/'INDEX.html').write_text('<!doctype html><meta charset="utf-8"><h1>P1 offline teachers, NOT network outputs</h1>'+''.join(f'<p><img src="contact_{i}.jpg" width="1280"></p>' for i in range(1,6)),encoding='utf-8')

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',default='reports/paired_v5/P1/targets_12');args=ap.parse_args();assert not (ROOT/args.out/'params.json').exists(),'Use a new target version directory';preview(ROOT/args.out)
