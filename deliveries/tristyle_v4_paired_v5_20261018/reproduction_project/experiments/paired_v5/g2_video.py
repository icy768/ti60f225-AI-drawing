"""Held-out 640..789 video: one input-derived flow/mask cache for all models.

Host timings never measure FPGA performance. Reduced mode runs at 320x240 and
displays at 640x480. No frame from this cache may be used in optimization.
"""
from pathlib import Path
import argparse, hashlib, json, sys, time
import cv2
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
V3=Path(json.loads((ROOT/'baseline/manifest.json').read_text())['V3_root'])
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def prepare(folder):
    assert not folder.exists(),'Preserve existing cache'
    folder.mkdir(parents=True)
    meta_path=V3/'data/video/train_pairs/manifest.json'
    meta=json.loads(meta_path.read_text());source=V3/meta['source']
    assert max(p['frame']+1 for p in meta['pairs'])<640
    cap=cv2.VideoCapture(str(source));assert cap.isOpened()
    cap.set(cv2.CAP_PROP_POS_FRAMES,640)
    gy,gx=np.mgrid[:480,:640].astype('float32');prev=None;rows=[]
    for frame in range(640,790):
        ok,bgr=cap.read();assert ok,frame
        rgb=cv2.cvtColor(cv2.resize(bgr,(640,480),interpolation=cv2.INTER_AREA),cv2.COLOR_BGR2RGB)
        cut=False;mx=gx.copy();my=gy.copy();mask=np.zeros((480,640),bool)
        if prev is not None:
            ga=cv2.cvtColor(prev,cv2.COLOR_RGB2GRAY);gb=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
            cut=float(np.abs(ga.astype(float)-gb).mean())>30
            if not cut:
                fl=cv2.calcOpticalFlowFarneback(gb,ga,None,.5,3,15,3,5,1.2,0)
                mx,my=gx+fl[...,0],gy+fl[...,1]
                wp=cv2.remap(prev.astype('float32')/255,mx,my,cv2.INTER_LINEAR)
                diff=np.abs(wp-rgb/255).mean(2)
                mask=(diff<.08)&(mx>1)&(mx<638)&(my>1)&(my<478)
        assert np.isfinite(mx).all() and np.isfinite(my).all()
        p=folder/f'{frame:06d}.npz'
        np.savez_compressed(p,rgb=rgb,mx=mx,my=my,mask=mask,cut=cut)
        rows.append({'frame':frame,'path':p.name,'sha256':sha(p),'scene_cut':cut,'valid_fraction':float(mask.mean())})
        prev=rgb
        if frame%20==19:print('CACHE_FRAME',frame,flush=True)
    cap.release()
    out={'source':str(source),'source_sha256':sha(source),'training_manifest_sha256':sha(meta_path),
         'max_training_frame':max(p['frame']+1 for p in meta['pairs']),
         'fps':meta['fps'],'rows':rows,'inference_only':True,'size':[640,480],
         'license':'Sintel trailer, Blender Foundation, CC BY3.0; original source license retained in V3',
         'protocol':'current-to-previous Farneback .5/3/15/3/5/1.2; cut>30; input remap MAE<.08; border excluded',
         'warning':'Visibility mask is an input-photometric proxy, not ground-truth flow/occlusion.'}
    (folder/'manifest.json').write_text(json.dumps(out,indent=2));print('FLOW_CACHE_COMPLETE',len(rows),flush=True)

def evaluate(cache,checkpoint,out,mode,device):
    import torch
    sys.path.insert(0,str(ROOT/'diagnostics'))
    from v3_access import model_for_state,STYLES
    torch.set_num_threads(3)
    manifest=json.loads((cache/'manifest.json').read_text())
    assert manifest['inference_only'] and [r['frame'] for r in manifest['rows']]==list(range(640,790))
    ck=torch.load(checkpoint,map_location='cpu',weights_only=False)
    if ck['model']['experts.1.head.conv.weight'].shape[0]==17:
        from palette_model import model_for_state
    net=model_for_state(ck['model']).to(device).eval();net.load_state_dict(ck['model'])
    out.mkdir(parents=True,exist_ok=False)
    video=cv2.VideoWriter(str(out/'heldout.mp4'),cv2.VideoWriter_fourcc(*'mp4v'),manifest['fps'],(2560,480));assert video.isOpened()
    previous=None;records=[]
    with torch.no_grad():
        for row in manifest['rows']:
            p=cache/row['path'];assert sha(p)==row['sha256']
            z=np.load(p);rgb=z['rgb'];x=torch.from_numpy(rgb.copy()).permute(2,0,1)[None].float().to(device)/255
            if mode=='reduced320':x=torch.nn.functional.interpolate(x,(240,320),mode='bilinear',align_corners=False,antialias=True)
            ys=[];rec={'frame':row['frame'],'scene_cut':row['scene_cut'],'valid_fraction':row['valid_fraction']}
            for ei,style in enumerate(STYLES):
                start=time.perf_counter();y=net(x,ei).float().clamp(0,1)
                if mode=='reduced320':y=torch.nn.functional.interpolate(y,(480,640),mode='bilinear',align_corners=False)
                if device=='cuda':torch.cuda.synchronize()
                rec[style+'_host_ms']=1000*(time.perf_counter()-start)
                ys.append(y[0].permute(1,2,0).cpu().numpy())
                if previous is not None and not row['scene_cut'] and z['mask'].any():
                    warped=cv2.remap(previous[ei],z['mx'],z['my'],cv2.INTER_LINEAR)
                    rec[style+'_warp_MAE']=float(np.abs(warped-ys[-1]).mean(2)[z['mask']].mean())
            panels=[rgb.copy()]+[np.ascontiguousarray((v*255).round().astype('uint8')) for v in ys]
            for im,label in zip(panels,['INPUT']+list(STYLES)):
                cv2.putText(im,label,(8,22),cv2.FONT_HERSHEY_SIMPLEX,.6,(255,255,255),2)
            montage=np.concatenate(panels,1)
            video.write(cv2.cvtColor(montage,cv2.COLOR_RGB2BGR))
            if row['frame']%30==10:cv2.imwrite(str(out/f'frame_{row["frame"]}.jpg'),cv2.cvtColor(montage,cv2.COLOR_RGB2BGR))
            records.append(rec);previous=ys
            if row['frame']%20==19:print('EVALUATED_FRAME',row['frame'],flush=True)
    video.release()
    summary={s:{'warp_MAE_mean':float(np.mean([r[s+'_warp_MAE'] for r in records if s+'_warp_MAE' in r])),
                'pairs':sum(s+'_warp_MAE' in r for r in records)} for s in STYLES}
    (out/'metrics.json').write_text(json.dumps({'checkpoint':str(checkpoint),'checkpoint_sha256':sha(checkpoint),
        'cache_manifest_sha256':sha(cache/'manifest.json'),'mode':mode,'size':[640,480],
        'internal_size':[320,240] if mode=='reduced320' else [640,480],
        'note':'FP32 raw neural outputs; reduced320 is reduced-resolution mode; host timings are NOT FPGA fps.',
        'summary':summary,'rows':records},indent=2))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--cache',required=True);ap.add_argument('--prepare',action='store_true')
    ap.add_argument('--checkpoint');ap.add_argument('--out');ap.add_argument('--mode',choices=['native640','reduced320'],default='native640');ap.add_argument('--device',default='cuda')
    a=ap.parse_args();cv2.setNumThreads(2)
    if a.prepare:prepare(ROOT/a.cache)
    else:evaluate(ROOT/a.cache,ROOT/a.checkpoint,ROOT/a.out,a.mode,a.device)
