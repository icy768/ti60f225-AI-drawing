"""Source-only audit of hzy46 FNS versus the frozen StyleCam v6 graph.

Does not install TensorFlow, run the external model, or modify model weights.
MAC counts cover convolutions only; normalization and DDR traffic are excluded.
"""
import hashlib
import json
import urllib.request
from pathlib import Path

import torch
from tinystyle import TinyStyleNet, macs_per_pixel
from teacher import TransformerNet, teacher_macs_per_pixel


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "StyleCam-source-audit"})
    with urllib.request.urlopen(req, timeout=45) as response:
        return response.read()


def main():
    root = Path(__file__).resolve().parents[1]
    out = root / "audits/external_fns_hzy46_20261005"
    out.mkdir(parents=True, exist_ok=True)
    repo = "hzy46/fast-neural-style-tensorflow"
    commit = json.loads(fetch(f"https://api.github.com/repos/{repo}/commits/master"))["sha"]
    listing = json.loads(fetch(f"https://api.github.com/repos/{repo}/contents?ref={commit}"))
    provenance = []
    for name in ["README.md", "model.py", "losses.py", "conf/wave.yml"]:
        url = f"https://raw.githubusercontent.com/{repo}/{commit}/{name}"
        data = fetch(url)
        target = out / "source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        provenance.append({"file": name, "url": url, "sha256": hashlib.sha256(data).hexdigest()})
    # model.py: outer REFLECT padding of ten pixels on each side;
    # conv1, conv2, conv3; ten residual convolutions; two resize/stride
    # convolutions; final convolution. No convolution biases or IN affine.
    h, w = 480 + 20, 640 + 20
    specs = [("conv1", 3, 32, 9, h, w), ("conv2", 32, 64, 3, h//2, w//2),
             ("conv3", 64, 128, 3, h//4, w//4)]
    specs += [(f"res{i}_{j}", 128, 128, 3, h//4, w//4) for i in range(1, 6) for j in (1, 2)]
    specs += [("deconv1", 128, 64, 3, h//2, w//2),
              ("deconv2", 64, 32, 3, h, w), ("deconv3", 32, 3, 9, h, w)]
    rows = [{"name": n, "weight_count": ci*co*k*k, "output_hw": [hh, ww],
             "macs": ci*co*k*k*hh*ww} for n, ci, co, k, hh, ww in specs]
    weights = sum(r["weight_count"] for r in rows)
    external_macs = sum(r["macs"] for r in rows)
    ck = torch.load(root / "runs/art_styles_c24_graphic_v6/student.pt", map_location="cpu", weights_only=False)
    net = TinyStyleNet(**ck["cfg"])
    net.load_state_dict(ck["sd"])
    local_macs = round(macs_per_pixel(net.specs)[0]*640*480)
    report = {
        "date": "2026-10-05", "repository": repo, "source_commit": commit,
        "source_files": provenance, "repository_root_files": [x["name"] for x in listing],
        "license_files_at_root": [x["name"] for x in listing if "license" in x["name"].lower() or "copying" in x["name"].lower()],
        "external_fns": {"conv_weights": weights, "fp32_weight_bytes": weights*4,
                         "hypothetical_int8_weight_bytes": weights,
                         "vga_conv_macs_with_actual_outer_padding": external_macs,
                         "conv_layers": rows, "model_executed": False,
                         "scope": "source-derived counts; no FPS or visual quality measured"},
        "local_v6": {"cfg": ck["cfg"], "styles": ck["styles"],
                     "parameters": sum(p.numel() for p in net.parameters()),
                     "vga_conv_macs": local_macs},
        "local_standard_pytorch_teacher": {"parameters": sum(p.numel() for p in TransformerNet().parameters()),
                                            "vga_conv_macs": round(teacher_macs_per_pixel()*640*480)},
        "external_to_v6_conv_macs_ratio": external_macs/local_macs,
        "external_vga_required_conv_gmac_per_second_at_15fps": external_macs*15/1e9,
        "same_algorithm_family": True, "same_deployable_graph": False,
        "contest_absolute_psnr_ssim_threshold_specified": False,
        "hardware_realtime_validated": False,
    }
    (out / "audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in ("source_files", "external_fns", "repository_root_files")}, ensure_ascii=False, indent=2))
    print("external_weight_count", weights, "external_VGA_conv_MAC", external_macs)


if __name__ == "__main__":
    main()
