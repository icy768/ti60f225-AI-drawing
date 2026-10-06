"""Assert unchanged v8/v9 deployment graph and save the verification record."""
import argparse
import hashlib
import json
from pathlib import Path

import torch

from tinystyle import TinyStyleNet, macs_per_pixel
from train import ROOT


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--base', default='runs/art_styles_c24_structure_v8_pilot900/student.pt')
    p.add_argument('--candidate', default='runs/art_styles_c24_aic_v9_1200/student.pt')
    p.add_argument('--out', default='audits/v9_aic_20261004/graph_check.json')
    args = p.parse_args()
    root = Path(ROOT)
    a = torch.load(root/args.base, map_location='cpu', weights_only=False)
    b = torch.load(root/args.candidate, map_location='cpu', weights_only=False)
    expected = dict(C=24, Fc=16, n_res=4, n_styles=3, norm='in', block='dw1')
    assert a['cfg'] == b['cfg'] == expected
    assert a['styles'] == b['styles'] == ['van_gogh', 'ukiyo_e', 'ink_landscape']
    assert list(a['sd']) == list(b['sd'])
    assert all(a['sd'][k].shape == b['sd'][k].shape for k in a['sd'])
    net = TinyStyleNet(**b['cfg']).eval()
    net.load_state_dict(b['sd'])
    params = sum(p.numel() for p in net.parameters())
    macs = macs_per_pixel(net.specs)[0]*640*480
    assert params == 11028 and macs == 339148800
    with torch.no_grad():
        x = torch.rand(1, 3, 480, 640)
        output_shapes = [list(net(x, torch.tensor([si])).shape) for si in range(3)]
    assert output_shapes == [[1, 3, 480, 640]]*3
    result = dict(base=args.base, candidate=args.candidate,
                  base_sha256=sha(root/args.base), candidate_sha256=sha(root/args.candidate),
                  cfg=b['cfg'], styles=b['styles'], state_keys=len(b['sd']), params=params,
                  conv_MACs_VGA=macs, input_shape=list(x.shape), output_shapes=output_shapes,
                  graph_changed=False, quantization_validated=False, board_validated=False)
    path = root/args.out
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
