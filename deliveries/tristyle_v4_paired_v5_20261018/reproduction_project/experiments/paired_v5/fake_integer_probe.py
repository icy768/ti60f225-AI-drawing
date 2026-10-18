"""CPU layerwise fake/oneDNN discrepancy diagnostic, without changing weights."""
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


def main():
    torch.set_num_threads(3)
    torch.backends.quantized.engine = 'onednn'
    out = ROOT/'reports/paired_v5/P4/qat_smoke_v7_r2'
    state = torch.load(out/'smoke_fake_int8_state.pt', weights_only=True)
    fp = torch.load(out/'smoke_fp32.pt', map_location='cpu', weights_only=False)['model']
    fake = qm.prepared(model_for_state(fp))
    fake.load_state_dict(state)
    fake.eval()
    fake.apply(torch.ao.quantization.disable_observer)
    integer = qm.to_int(fake)
    captured = [{}, {}]
    hooks = []
    for i, model in enumerate([fake, integer]):
        for name, module in model.named_modules():
            if 'Conv' in type(module).__name__:
                def hook(mod, args, output, index=i, key=name):
                    y = output.detach()
                    captured[index][key] = y.dequantize() if y.is_quantized else y.clone()
                hooks.append(module.register_forward_hook(hook))
    path = sorted((V3/'data/claude_targets/content/validation').glob('*.png'))[0]
    x = torch.from_numpy(np.array(Image.open(path).convert('RGB').resize((80,64)), copy=True)).permute(2,0,1)[None].float()/255
    rows = []
    with torch.no_grad():
        for style in range(3):
            for c in captured: c.clear()
            yf, yi = fake(x, style), integer(x, style)
            layers = []
            for name in captured[0].keys() & captured[1].keys():
                diff = (captured[0][name]-captured[1][name]).abs()
                scale = float(dict(fake.named_modules())[name].activation_post_process.scale)
                layers.append({'name': name, 'maxabs': float(diff.max()), 'meanabs': float(diff.mean()),
                               'max_output_codes': float(diff.max())/scale, 'activation_scale': scale})
            rows.append({'style': style, 'final_maxabs': float((yf-yi).abs().max()),
                         'final_meanabs': float((yf-yi).abs().mean()),
                         'layers': sorted(layers, key=lambda z:z['maxabs'], reverse=True)})
    for hook in hooks: hook.remove()
    result = {'scope': '8-step rehearsal layerwise fake vs oneDNN on one 80x64 validation image; no updates',
              'input': str(path), 'input_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
              'fake_state_sha256': hashlib.sha256((out/'smoke_fake_int8_state.pt').read_bytes()).hexdigest(),
              'rows': rows, 'diagnosis': 'Measured discrepancy only; no invented numerical acceptance threshold.'}
    (out/'FAKE_ONEDNN_LAYERS.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps([{k:v for k,v in row.items() if k!='layers'} for row in rows]))


if __name__ == '__main__': main()
