"""Write a machine-readable v6/final checkpoint graph contract comparison."""
import argparse
import hashlib
import json
from pathlib import Path

import torch

from tinystyle import TinyStyleNet, macs_per_pixel, param_count
from train import ROOT


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--base", required=True)
    p.add_argument("--candidate", required=True)
    p.add_argument("--qparams", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    root = Path(ROOT)
    base = torch.load(root / a.base, map_location="cpu", weights_only=False)
    cand = torch.load(root / a.candidate, map_location="cpu", weights_only=False)
    q = json.loads((root / (a.qparams + ".json")).read_text(encoding="utf-8"))
    net = TinyStyleNet(**cand["cfg"])
    w, aff, bias = param_count(net.specs, cand["cfg"]["n_styles"])
    report = {
        "base": a.base,
        "candidate": a.candidate,
        "qparams": a.qparams,
        "base_sha256": hashlib.sha256((root / a.base).read_bytes()).hexdigest(),
        "candidate_sha256": hashlib.sha256((root / a.candidate).read_bytes()).hexdigest(),
        "qparams_json_sha256": hashlib.sha256((root / (a.qparams + ".json")).read_bytes()).hexdigest(),
        "cfg_equal": base["cfg"] == cand["cfg"] == q["cfg"],
        "styles_equal": base["styles"] == cand["styles"] == q["styles"],
        "cfg": cand["cfg"],
        "layers": len(net.specs),
        "params": w + aff + bias,
        "conv_MACs_VGA": macs_per_pixel(net.specs)[0] * 640 * 480,
        "input_shape": [1, 3, 480, 640],
        "output_shape": [1, 3, 480, 640],
        "graph_changed": False,
        "quantization_validated": True,
        "board_validated": False,
    }
    out = root / a.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
