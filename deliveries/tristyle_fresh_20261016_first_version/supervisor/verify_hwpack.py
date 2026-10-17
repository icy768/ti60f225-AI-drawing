"""Execute both serialized formats on the same real RGB inputs; no FPGA claims."""
import argparse, json, pathlib, sys
import numpy as np
from PIL import Image
import torch
ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / 'claude_impl'))
from int_ref import IntGraph
ap = argparse.ArgumentParser(); ap.add_argument('deployment'); a = ap.parse_args(); dep = ROOT / a.deployment
torch.set_num_threads(3)
g0 = IntGraph(dep / 'tristyle_v3_all.bin'); g1 = IntGraph(dep / 'tristyle_v3_hw.bin')
cases = {'random': torch.randint(0, 256, (1, 3, 48, 64), generator=torch.Generator().manual_seed(95), dtype=torch.uint8)}
cases['black']=torch.zeros(1,3,48,64,dtype=torch.uint8)
cases['white']=torch.full((1,3,48,64),255,dtype=torch.uint8)
impulse=torch.zeros(1,3,48,64,dtype=torch.uint8);impulse[:,:,24,32]=255;cases['impulse']=impulse
for name in ('water_day', 'person_face'):
    im = np.array(Image.open(ROOT / 'data/test' / (name + '.png')).convert('RGB').resize((160, 120)), copy=True)
    cases[name] = torch.from_numpy(im).permute(2, 0, 1)[None]
rows = []
for name, x in cases.items():
    for s in range(3):
        d = (g0(x, s).to(torch.int16) - g1(x, s).to(torch.int16)).abs()
        rows.append({'case': name, 'style': s, 'max_LSB': int(d.max()), 'mean_LSB': float(d.float().mean())})
assert max(r['max_LSB'] for r in rows) == 0
res = {'status': f'MEASURED: fixed-record pack and JSON pack integer outputs bit-exact on these{len(rows)} cases', 'rows': rows,
       'fixed_pack_total_bytes': (dep / 'tristyle_v3_hw.bin').stat().st_size, 'max_observed_accumulator': g1.max_acc,
       'scope': 'CPU executable pack-only interpretation. Not RTL simulation, synthesis, board or FPGA throughput.'}
(dep / 'hwpack_verification.json').write_text(json.dumps(res, indent=2)); print(json.dumps(res, indent=2))
