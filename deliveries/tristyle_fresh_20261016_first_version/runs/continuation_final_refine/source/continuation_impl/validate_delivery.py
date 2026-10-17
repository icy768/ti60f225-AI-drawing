"""Fresh-process FLOAT/fake/oneDNN/native integer checks on the same QAT checkpoint."""
import argparse, hashlib, json, pathlib, sys, time
import numpy as np
from PIL import Image
import torch
from skimage.metrics import structural_similarity
ROOT=pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'claude_impl'))
from model import model_for_state, STYLES
from quantize import prepared
from int_ref import IntGraph
from train import save_grid, gallery

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('deployment'); ap.add_argument('--size',default='320x240'); ap.add_argument('--limit',type=int,default=0); ap.add_argument('--native-gallery',action='store_true'); a=ap.parse_args()
    dep=ROOT/a.deployment; torch.set_num_threads(3); torch.backends.quantized.engine='onednn'
    state=torch.load(dep/'tristyle_v3_fp32.pt',map_location='cpu',weights_only=False)['model']
    fp=model_for_state(state).eval(); fp.load_state_dict(state,strict=True)
    q=prepared(model_for_state(state)); q.load_state_dict(torch.load(dep/'fake_int8_state.pt',map_location='cpu',weights_only=True),strict=True)
    q.eval(); q.apply(torch.ao.quantization.disable_observer)
    q.apply(torch.ao.quantization.disable_fake_quant)
    x=torch.rand(1,3,48,64, generator=torch.Generator().manual_seed(195))
    with torch.inference_mode(): reload_error=max(float((fp(x,s)-q(x,s)).abs().max()) for s in range(3))
    assert reload_error<1e-4
    q.apply(torch.ao.quantization.enable_fake_quant)
    ts=torch.jit.load(str(dep/'tristyle_v3_int8.ts')).eval(); native=IntGraph(dep/'tristyle_v3_hw.bin')
    W,H=map(int,a.size.split('x')); assert W%8==H%8==0
    dest=dep/'normative_integer'; dest.mkdir(exist_ok=True); rows=[]; grids=[]
    paths=sorted((ROOT/'data/test').glob('*.png'))
    if a.limit: paths=paths[:a.limit]
    u8=lambda t: (t.clamp(0,1)*255).round().to(torch.uint8)
    arr=lambda t: t[0].permute(1,2,0).cpu().numpy()
    psnr=lambda d: -10*np.log10(max(float(np.mean((d.astype(float)/255)**2)),1e-12))
    with torch.inference_mode():
        for p in paths:
            im=np.array(Image.open(p).convert('RGB').resize((W,H),Image.Resampling.LANCZOS),copy=True)
            u=torch.from_numpy(im).permute(2,0,1)[None]; x=u.float()/255; images=[im]
            for s,name in enumerate(STYLES):
                yf,yq,yt=[arr(u8(m(x,s))) for m in (fp,q,ts)]
                t=time.perf_counter(); yi=arr(native(u,s)); dt=time.perf_counter()-t
                Image.fromarray(yi).save(dest/f'{p.stem}_{name}.png'); images.append(yi)
                d=yi.astype(np.int16)-yf.astype(np.int16); dq=yi.astype(np.int16)-yq.astype(np.int16); dtq=yi.astype(np.int16)-yt.astype(np.int16)
                rows.append({'scene':p.stem,'style':name,'size':[W,H], 'FLOAT_vs_native_PSNR':float(psnr(d)),
                    'FLOAT_vs_native_SSIM':float(structural_similarity(yf,yi,channel_axis=2)), 'native_vs_fake_max_LSB':int(abs(dq).max()),
                    'native_vs_fake_mean_LSB':float(abs(dq).mean()),'native_vs_onednn_max_LSB':int(abs(dtq).max()),
                    'native_vs_onednn_mean_LSB':float(abs(dtq).mean()),'native_CPU_seconds':dt})
                print('NATIVE',p.stem,name,round(dt,3),flush=True)
                (dep/'normative_progress.json').write_text(json.dumps({'completed_style_cases':len(rows),'last':rows[-1]},indent=1))
            grids.append((p.stem+' native integer',images))
    save_grid(grids,dep/'normative_integer_comparison.jpg')
    result={'status':'MEASURED CPU pack-only integer execution, fresh checkpoint reload', 'float_vs_fake_disabled_reload_maxabs':reload_error,
        'same_QAT_checkpoint':True,'size':[W,H],'scenes':len(paths),'pack_bytes':(dep/'tristyle_v3_hw.bin').stat().st_size,
        'pack_sha256':hashlib.sha256((dep/'tristyle_v3_hw.bin').read_bytes()).hexdigest(),'max_observed_accumulator':native.max_acc,
        'summary':{s:{k:float(np.mean([r[k] for r in rows if r['style']==s])) for k in ('FLOAT_vs_native_PSNR','FLOAT_vs_native_SSIM','native_vs_onednn_mean_LSB')} for s in STYLES},
        'rows':rows,'limitations':'PSNR/SSIM compare quantization retention only. oneDNN tie/requant arithmetic can differ from normative Q31 reference. No FPGA throughput/RTL evidence.'}
    (dep/'final_numeric_verification.json').write_text(json.dumps(result,indent=1))
    if a.native_gallery:
        d=dep/'float_native_size'; d.mkdir(exist_ok=True); gallery(fp,d,'cpu')
    print(json.dumps({k:v for k,v in result.items() if k!='rows'},indent=1))

if __name__=='__main__': main()
