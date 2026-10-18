"""Measured runtime regression test for the observed QAT conversion mismatch."""
from pathlib import Path
import hashlib
import json
import sys
import numpy as np
from PIL import Image
import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'diagnostics'))
from v3_access import V3, model_for_state
import quantize as qm
from consistent_qat import align_weight_fake_quant


def main():
    torch.set_num_threads(3)
    torch.backends.quantized.engine = 'onednn'
    base = ROOT/'reports/paired_v5/P4/qat_smoke_v7_r2'
    out = ROOT/'reports/paired_v5/P4/weight_qparam_fix_01'
    out.mkdir(exist_ok=False)
    state = torch.load(base/'smoke_fp32.pt', weights_only=False, map_location='cpu')['model']
    model = qm.prepared(model_for_state(state))
    model.load_state_dict(torch.load(base/'smoke_fake_int8_state.pt', weights_only=True))
    changed = align_weight_fake_quant(model)
    model.eval()
    model.apply(torch.ao.quantization.disable_observer)
    integer = qm.to_int(model)
    weight_errors = {}
    for n, m in model.named_modules():
        if hasattr(m, 'weight_fake_quant'):
            actual = dict(integer.named_modules())[n].weight().dequantize()
            expected = m.weight_fake_quant(m.weight).detach()
            weight_errors[n] = float((actual-expected).abs().max())
    assert max(weight_errors.values()) < 1e-6
    p = sorted((V3/'data/claude_targets/content/validation').glob('*.png'))[0]
    x = torch.from_numpy(np.array(Image.open(p).convert('RGB').resize((80,64)), copy=True)).permute(2,0,1)[None].float()/255
    rows = []
    with torch.no_grad():
        for s in range(3):
            diff = (model(x,s)-integer(x,s)).abs()
            rows.append({'style': s, 'fake_vs_onednn_maxabs': float(diff.max()), 'meanabs': float(diff.mean())})
    # Verify ordinary fake quantization still supplies finite nonzero gradients.
    model.train()
    model.zero_grad(set_to_none=True)
    loss = model(x[:,:,:32,:40], 0).square().mean()
    loss.backward()
    grads = [p.grad for p in model.parameters() if p.grad is not None]
    assert grads and all(torch.isfinite(g).all() for g in grads)
    assert sum(float(g.abs().sum()) for g in grads) > 0
    for pth in [Path(__file__), Path(__file__).with_name('consistent_qat.py')]:
        (out/pth.name).write_bytes(pth.read_bytes())
    result = {'runtime': torch.__version__, 'changed_convs': changed, 'max_weight_difference': max(weight_errors.values()),
              'same_weights_no_training': True, 'finite_nonzero_gradient': True, 'rows': rows,
              'input_sha256': hashlib.sha256(p.read_bytes()).hexdigest(),
              'limitations': 'One low-resolution input, not full retention or final QAT. Integer rounding remains independently validated.'}
    (out/'RESULT.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='changed_convs'}))


if __name__ == '__main__': main()
