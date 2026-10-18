"""Re-export the 8-step rehearsal weights with aligned QAT scales; no training."""
from pathlib import Path
import hashlib
import json
import sys
import torch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'diagnostics'))
from v3_access import model_for_state
import quantize as qm
from consistent_qat import align_weight_fake_quant


def main():
    torch.set_num_threads(3)
    torch.backends.quantized.engine='onednn'
    src=ROOT/'reports/paired_v5/P4/qat_smoke_v7_r2'
    dest=ROOT/'reports/paired_v5/P4/qat_aligned_chain_01'
    dest.mkdir(exist_ok=False)
    checkpoint=torch.load(src/'smoke_fp32.pt',weights_only=False,map_location='cpu')
    fp=model_for_state(checkpoint['model']).eval();fp.load_state_dict(checkpoint['model'])
    fake=qm.prepared(fp)
    fake.load_state_dict(torch.load(src/'smoke_fake_int8_state.pt',weights_only=True))
    changed=align_weight_fake_quant(fake)
    fake.eval();fake.apply(torch.ao.quantization.disable_observer)
    integer=qm.to_int(fake)
    size=qm.pack(integer,fp,dest/'smoke_all.bin')
    torch.jit.script(integer).save(str(dest/'smoke_int8.ts'))
    torch.save(fake.state_dict(),dest/'smoke_fake_int8_state.pt')
    # Preserve exact floating weights from the source rehearsal, not a new candidate.
    (dest/'smoke_fp32.pt').write_bytes((src/'smoke_fp32.pt').read_bytes())
    for p in [Path(__file__),Path(__file__).with_name('consistent_qat.py')]:
        (dest/p.name).write_bytes(p.read_bytes())
    (dest/'RESULT.json').write_text(json.dumps({'source':str(src),'source_state_sha256':hashlib.sha256((src/'smoke_fake_int8_state.pt').read_bytes()).hexdigest(),
       'additional_training_steps':0,'original_qat_steps':8,'weight_qparams_aligned':len(changed),'pack':size,
       'scope':'P4 conversion fix rehearsal only; no candidate promotion'},indent=2),encoding='utf-8')
    print('ALIGNED_EXPORT_COMPLETE',flush=True)


if __name__=='__main__':main()
