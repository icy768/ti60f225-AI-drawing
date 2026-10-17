"""Real held-out video, input-flow warping and occlusion rejection. No FPGA claims."""
import argparse,json,time,pathlib
import cv2,numpy as np,torch
from model import TriStyle,STYLES
from data import ROOT
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--checkpoint',required=True);ap.add_argument('--output',default='reports/video');ap.add_argument('--frames',type=int,default=120);ap.add_argument('--integer',action='store_true');a=ap.parse_args()
    torch.set_num_threads(4);torch.backends.quantized.engine='onednn';device='cpu' if a.integer else 'cuda'
    if a.integer:m=torch.jit.load(a.checkpoint,map_location='cpu').eval()
    else:
        m=TriStyle().to(device).eval();m.load_state_dict(torch.load(a.checkpoint,map_location='cpu',weights_only=False)['model'])
    meta=json.loads((ROOT/'data/video/train_pairs/manifest.json').read_text());cap=cv2.VideoCapture(str(ROOT/meta['source']));cap.set(cv2.CAP_PROP_POS_FRAMES,meta['evaluation_start_frame']);out=ROOT/a.output;out.mkdir(parents=True,exist_ok=True)
    # Source is 24 fps. Preserve source fps here: benchmark distinct from 30->15 FPGA policy.
    writer=cv2.VideoWriter(str(out/'comparison.mp4'),cv2.VideoWriter_fourcc(*'mp4v'),meta['fps'],(1280,240));prev=None;prevy=None;rows=[]
    with torch.inference_mode():
        for i in range(a.frames):
            ok,bgr=cap.read()
            if not ok:break
            bgr=cv2.resize(bgr,(320,240));rgb=bgr[:,:,::-1].copy();x=torch.from_numpy(rgb).permute(2,0,1).unsqueeze(0).to(device).float()/255.;ys=[]
            for s in range(3):
                t=time.perf_counter();y=m(x,s)
                if device=='cuda':torch.cuda.synchronize()
                elapsed=time.perf_counter()-t;ys.append(y[0].clamp(0,1).permute(1,2,0).cpu().numpy());rows.append({'frame':i,'style':STYLES[s],'host_inference_sec':elapsed})
            if prev is not None:
                ga=cv2.cvtColor(prev,cv2.COLOR_RGB2GRAY);gb=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY);flow=cv2.calcOpticalFlowFarneback(gb,ga,None,.5,3,15,3,5,1.2,0)
                gy,gx=np.mgrid[:240,:320].astype(np.float32);mx=gx+flow[:,:,0];my=gy+flow[:,:,1];warped=cv2.remap(prev.astype(np.float32)/255.,mx,my,cv2.INTER_LINEAR)
                diff=np.abs(warped-rgb/255.).mean(2);mask=(diff<.12)&(mx>1)&(mx<318)&(my>1)&(my<238)
                cut=float(np.abs(ga.astype(float)-gb.astype(float)).mean())>35
                for s in range(3):
                    wy=cv2.remap(prevy[s],mx,my,cv2.INTER_LINEAR);err=np.abs(wy-ys[s]).mean(2)
                    rows[-3+s].update({'flow_warp_MAE_visible':float(err[mask].mean()) if mask.any() and not cut else None,'input_flow_warp_MAE_visible':float(diff[mask].mean()) if mask.any() and not cut else None,'valid_fraction':float(mask.mean()),'scene_cut_skipped':cut})
            panels=[bgr]+[(v[:,:,::-1]*255).round().astype(np.uint8) for v in ys]
            for panel,label in zip(panels,['input']+list(STYLES)):cv2.putText(panel,label,(8,20),cv2.FONT_HERSHEY_SIMPLEX,.55,(0,0,0),3);cv2.putText(panel,label,(8,20),cv2.FONT_HERSHEY_SIMPLEX,.55,(255,255,255),1)
            frame=np.concatenate(panels,axis=1);writer.write(frame)
            if i in [0,30,60,90]:cv2.imwrite(str(out/f'frame_{i:04d}.jpg'),frame)
            prev=rgb;prevy=ys
    writer.release();cap.release();summary={}
    for s in STYLES:
        rs=[r for r in rows if r['style']==s];es=[r['flow_warp_MAE_visible'] for r in rs if r.get('flow_warp_MAE_visible') is not None]
        summary[s]={'mean_flow_warp_MAE':float(np.mean(es)) if es else None,'host_mean_ms':1000*float(np.mean([r['host_inference_sec'] for r in rs])),'valid_pairs':len(es)}
    (out/'metrics.json').write_text(json.dumps({'checkpoint':a.checkpoint,'source':meta['source'],'heldout_start_frame':meta['evaluation_start_frame'],'fps':meta['fps'],'resolution':[320,240],'integer':a.integer,'summary':summary,'frames':rows,'limitations':'Farneback input flow and photometric visibility mask are approximate; metric alone does not certify temporal quality. CPU/GPU timing is not FPGA fps.'},indent=2));print(json.dumps(summary,indent=2),flush=True)
if __name__=='__main__':main()
