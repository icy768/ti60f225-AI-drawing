"""Full fixed17 same-checkpoint FP32/fake/normative-integer retention, CPU only."""
from pathlib import Path
import argparse
import hashlib
import json
import sys
import time
import numpy as np
from PIL import Image
import torch
from torch.nn import functional as F
from skimage.metrics import structural_similarity

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'diagnostics'))
from v3_access import model_for_state
from int_ref import IntGraph
from hwpack import write_hw
import quantize as qm
from consistent_qat import align_weight_fake_quant, simulate_int32_bias
STYLES=('vangogh','ukiyoe','ink')


def stats(reference, candidate):
    a=reference[0].permute(1,2,0).numpy().astype(np.float64)
    b=candidate[0].permute(1,2,0).numpy().astype(np.float64)
    mse=float(np.mean((a-b)**2))
    return {'PSNR_dB':float(-10*np.log10(max(mse,1e-12))),
            'SSIM':float(structural_similarity(a,b,data_range=1.,channel_axis=2)),
            'MAE_LSB':float(np.abs(a-b).mean()*255),
            'maxabs_LSB':float(np.abs(a-b).max()*255)}


def save(x,path):
    im=(x[0].permute(1,2,0).clamp(0,1).numpy()*255).round().astype('uint8')
    Image.fromarray(im).save(path)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--deployment',required=True);ap.add_argument('--out',required=True)
    a=ap.parse_args();d=(ROOT/a.deployment).resolve();out=(ROOT/a.out).resolve()
    assert ROOT in out.parents
    out.mkdir(exist_ok=False,parents=True)
    (out/'source.py').write_bytes(Path(__file__).read_bytes())
    (out/'consistent_qat.py').write_bytes(Path(__file__).with_name('consistent_qat.py').read_bytes())
    torch.set_num_threads(3);torch.backends.quantized.engine='onednn'
    ck=torch.load(d/'fp32.pt',map_location='cpu',weights_only=False)['model']
    fp=model_for_state(ck).eval();fp.load_state_dict(ck)
    fake=qm.prepared(model_for_state(ck));align_weight_fake_quant(fake)
    fake.load_state_dict(torch.load(d/'fake_int8_state.pt',weights_only=True));fake.eval()
    fake.apply(torch.ao.quantization.disable_observer)
    simulate_int32_bias(fake,json.loads((d/'input_scales.json').read_text()))
    size=write_hw(d/'all_styles.bin',d/'all_styles_hw.bin',320,240)
    (d/'hardware_pack_bytes.json').write_text(json.dumps(size,indent=2))
    integer=IntGraph(d/'all_styles_hw.bin')
    entries=json.loads((ROOT/'data/fixed_test_manifest.json').read_text());assert len(entries)==17
    rows=[]
    with torch.no_grad():
        for mode in ('native','internal320x240_REDUCED_RESOLUTION'):
            folder=out/mode;folder.mkdir()
            for name,meta in entries.items():
                p=Path(meta['path']);assert hashlib.sha256(p.read_bytes()).hexdigest()==meta['sha256']
                orig=torch.from_numpy(np.array(Image.open(p).convert('RGB'),copy=True)).permute(2,0,1)[None]
                if mode=='native':
                    h,w=orig.shape[-2:];u=F.pad(orig,(0,-w%8,0,-h%8),mode='replicate')
                else:
                    # Apply identical uint8 deployment input to all three backends.
                    u=F.interpolate(orig.float(),(240,320),mode='bilinear',align_corners=False,antialias=True).round().clamp(0,255).to(torch.uint8)
                    h,w=240,320
                x=u.float()/255
                for style,s in enumerate(STYLES):
                    start=time.perf_counter()
                    yf=fp(x,style).clamp(0,1)[:,:,:h,:w]
                    yq=fake(x,style).clamp(0,1)[:,:,:h,:w]
                    yi=integer(u,style).float()[:,:,:h,:w]/255
                    row={'mode':mode,'scene':name,'style':s,'input_H_W':[h,w],
                         'FP32_vs_fake':stats(yf,yq),'FP32_vs_integer':stats(yf,yi),
                         'fake_vs_integer':stats(yq,yi),'host_CPU_seconds':time.perf_counter()-start}
                    rows.append(row)
                    for label,y in [('fp32',yf),('fake',yq),('integer',yi)]:
                        save(y,folder/f'{Path(name).stem}_{s}_{label}.png')
                    print('RETENTION',mode,name,s,json.dumps(row['FP32_vs_integer']),flush=True)
                    (out/'progress.json').write_text(json.dumps({'completed':len(rows),'last':row},indent=2))
                    (out/'rows_partial.json').write_text(json.dumps(rows,indent=2))
    summary={}
    for mode in ('native','internal320x240_REDUCED_RESOLUTION'):
        summary[mode]={}
        for s in STYLES:
            selected=[z for z in rows if z['mode']==mode and z['style']==s]
            summary[mode][s]={pair:{metric:float(np.mean([z[pair][metric] for z in selected])) for metric in selected[0][pair]} for pair in ('FP32_vs_fake','FP32_vs_integer','fake_vs_integer')}
    report={'same_checkpoint':True,'checkpoint_sha256':hashlib.sha256((d/'fp32.pt').read_bytes()).hexdigest(),
            'protocol':'All backends same uint8 input; native pads replicate to multiple8 then crops. Reduced metrics at internal320x240, not interpolated display.',
            'parameter_count':sum(p.numel() for p in fp.parameters()),
            'parameter_storage_bytes':sum(p.numel()*(4 if n.endswith('bias') else 1) for n,p in fp.named_parameters()),
            'complete_fixed_package_bytes':size['total_bytes'],
            'rows':rows,'summary':summary,'max_actual_accumulator':integer.max_acc,
            'artistic_passed':False,'FPGA_fps_measured':False,
            'note':'Retention metrics only. No invented PSNR/SSIM acceptance cutoff or artistic promotion.'}
    (out/'RESULT.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    (out/'source.py').write_bytes(Path(__file__).read_bytes())
    print('FULL17_RETENTION_COMPLETE',flush=True)


if __name__=='__main__':main()
