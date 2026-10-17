"""Real optical-flow pairs from an openly licensed movie; held-out late segment."""
import pathlib,json,cv2,numpy as np
ROOT=pathlib.Path(__file__).resolve().parent
src=ROOT/'data/video/sintel_trailer-480p.mp4';cap=cv2.VideoCapture(str(src));fps=cap.get(cv2.CAP_PROP_FPS);n=int(cap.get(cv2.CAP_PROP_FRAME_COUNT));out=ROOT/'data/video/train_pairs';out.mkdir(exist_ok=True)
prev=None;records=[];i=0
while True:
    ok,bgr=cap.read()
    if not ok:break
    # First half used for training. Last 10 seconds reserved for test only.
    if 60<=i<min(n//2,700) and i%3==0:
        a=cv2.resize(bgr,(256,192),interpolation=cv2.INTER_AREA)
        if prev is not None:
            ga=cv2.cvtColor(prev,cv2.COLOR_BGR2GRAY);gb=cv2.cvtColor(a,cv2.COLOR_BGR2GRAY)
            if np.abs(ga.astype(float)-gb.astype(float)).mean()<35 and ga.std()>12 and gb.std()>12:
                # backward flow locates old-frame pixels for each new-frame pixel
                flow=cv2.calcOpticalFlowFarneback(gb,ga,None,.5,3,15,3,5,1.2,0)
                p=out/f'{i:05d}.npz';np.savez_compressed(p,a=prev[:,:,::-1].copy(),b=a[:,:,::-1].copy(),backward=flow)
                records.append({'frame':i,'file':str(p.relative_to(ROOT))})
        prev=a
    i+=1
cap.release();(out/'manifest.json').write_text(json.dumps({'source':str(src.relative_to(ROOT)),'fps':fps,'frames':n,'pairs':records,'evaluation_start_frame':max(n-240,n//2)},indent=2));print('VIDEO PAIRS',len(records),fps,n,flush=True)
