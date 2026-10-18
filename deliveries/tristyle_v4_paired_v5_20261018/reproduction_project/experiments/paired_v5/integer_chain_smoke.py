"""P4 pack-only integer rehearsal on the same 8-step QAT checkpoint."""
from pathlib import Path
import argparse,json,sys,time,hashlib
import numpy as np
import torch
from PIL import Image
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'diagnostics'))
from v3_access import V3,model_for_state
from int_ref import IntGraph
from hwpack import write_hw
import quantize as qm

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--deployment',required=True);a=ap.parse_args()
    d=ROOT/a.deployment;assert (d/'RESULT.json').exists()
    torch.set_num_threads(3);torch.backends.quantized.engine='onednn'
    report=write_hw(d/'smoke_all.bin',d/'smoke_hw.bin',320,240)
    (d/'smoke_hw_bytes.json').write_text(json.dumps(report,indent=2))
    first,second=IntGraph(d/'smoke_all.bin'),IntGraph(d/'smoke_hw.bin')
    ck=torch.load(d/'smoke_fp32.pt',map_location='cpu',weights_only=False)
    fp=model_for_state(ck['model']).eval();fp.load_state_dict(ck['model'])
    fake=qm.prepared(model_for_state(ck['model']))
    if json.loads((d/'RESULT.json').read_text()).get('weight_qparams_aligned'):
        from consistent_qat import align_weight_fake_quant
        align_weight_fake_quant(fake)
    fake.load_state_dict(torch.load(d/'smoke_fake_int8_state.pt',weights_only=True))
    fake.eval();fake.apply(torch.ao.quantization.disable_observer)
    ts=torch.jit.load(str(d/'smoke_int8.ts')).eval()
    cases={'black':torch.zeros(1,3,32,40,dtype=torch.uint8),'white':torch.full((1,3,32,40),255,dtype=torch.uint8),
           'random':torch.randint(0,256,(1,3,32,40),dtype=torch.uint8,generator=torch.Generator().manual_seed(37))}
    inputs=[]
    for p in sorted((V3/'data/claude_targets/content/validation').glob('*.png'))[:3]:
        im=np.array(Image.open(p).convert('RGB').resize((80,64)),copy=True)
        cases[p.stem]=torch.from_numpy(im).permute(2,0,1)[None].contiguous()
        inputs.append({'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    rows=[]
    with torch.no_grad():
        for name,u in cases.items():
            for style in range(3):
                start=time.perf_counter();yi=first(u,style);yh=second(u,style)
                assert torch.equal(yi,yh),'Fixed and compressed pack disagree'
                x=u.float()/255
                yf,yq,yt=[(m(x,style).clamp(0,1)*255).round().to(torch.uint8) for m in (fp,fake,ts)]
                diff=lambda z:(yi.int()-z.int()).abs()
                psnr=lambda z:float(-10*np.log10(max(float(((yi.double()-z.double())/255).square().mean()),1e-12)))
                row={'case':name,'style':style,'size':list(u.shape[-2:]),'compressed_vs_fixed_exact':True,
                     'native_vs_fake_max_LSB':int(diff(yq).max()),'native_vs_fake_mean_LSB':float(diff(yq).float().mean()),
                     'native_vs_onednn_max_LSB':int(diff(yt).max()),'native_vs_onednn_mean_LSB':float(diff(yt).float().mean()),
                     'native_vs_same_QAT_FP32_PSNR':psnr(yf),'CPU_seconds':time.perf_counter()-start}
                rows.append(row);print('INTEGER_CASE',name,style,flush=True)
                (d/'integer_progress.json').write_text(json.dumps({'completed':len(rows),'last':row},indent=2))
    result={'smoke_only':True,'same_checkpoint':True,'rows':rows,'validation_inputs':inputs,
            'fixed_record_bytes':report['total_bytes'],'max_actual_accumulator':max(first.max_acc,second.max_acc),
            'compressed_vs_fixed_all_exact':True,'artistic_passed':False,
            'limitations':'Only 32x40 synthetic + 80x64 three validation images; not full-resolution final retention, RTL, synthesis or board fps. oneDNN/fake rounding may differ from normative Q31.'}
    (d/'INTEGER_CHAIN_RESULT.json').write_text(json.dumps(result,indent=2));print('INTEGER_CHAIN_SMOKE_COMPLETE',flush=True)

if __name__=='__main__':main()
