"""Collect run evidence and check graph/float invariants of the trained candidate."""
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageDraw

from tinystyle import QCfg, TinyStyleNet, macs_per_pixel, param_count
from train import ROOT


def main():
    root = Path(ROOT)
    runs = ["art_styles_c24_strong_v3", "art_styles_c24_texture_v4",
            "art_styles_c24_differentiated_v5", "art_styles_c24_graphic_v6"]
    out = root / "audits/strong_art_training_20261004"
    out.mkdir(parents=True, exist_ok=True)
    checkpoints = []
    for run in runs:
        p = root / "runs" / run / "student.pt"
        c = torch.load(p, map_location="cpu", weights_only=False)
        checkpoints.append(dict(run=run, path=str(p), sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
                                steps=c["it"], cfg=c["cfg"], args=c["args"], qat=c["qat"],
                                seconds=c.get("seconds")))
    old = json.loads((root / "runs" / runs[0] / "eval_vga_200/summary.json").read_text(encoding="utf-8"))
    new = json.loads((root / "runs" / runs[-1] / "eval_vga_200/summary.json").read_text(encoding="utf-8"))
    assert old["n_coco"] == new["n_coco"] == 200
    assert [r["image"] for r in old["records"]] == [r["image"] for r in new["records"][:200]]
    final = torch.load(root / "runs" / runs[-1] / "student.pt", map_location="cpu", weights_only=False)
    assert all(c["cfg"] == final["cfg"] for c in checkpoints)
    net = TinyStyleNet(**final["cfg"]).cuda().eval(); net.load_state_dict(final["sd"])
    QCfg.enabled = False; QCfg.observe = False
    macs, _ = macs_per_pixel(net.specs)
    shape_tests = []
    with torch.no_grad():
        for h, w in ((480, 640), (720, 1280)):
            x = torch.full((1, 3, h, w), .5, device="cuda")
            for s in range(3):
                y = net(x, torch.tensor([s], device="cuda"))
                assert y.shape == x.shape and torch.isfinite(y).all()
                assert float(y.min()) >= 0 and float(y.max()) <= 1
                shape_tests.append(dict(width=w, height=h, style=final["styles"][s], finite=True,
                                        range=[float(y.min()), float(y.max())]))
    # These hashes were preserved in the existing PC-delivery audit.
    expected = {"sw/net_blob.h": "4dfc4629f32922639faa0765365365c3ff31642d609c0d0432c22a81c20c685a",
                "sw/in_params.h": "30948e193f40387abcc2efe907742513abe26ad31025b37f9576c045f02bdab4"}
    untouched = {}
    for path, sha in expected.items():
        actual = hashlib.sha256((root/path).read_bytes()).hexdigest()
        untouched[path] = dict(sha256=actual, equals_previous_delivery=actual == sha)
        assert actual == sha
    efx = Path("C:/CodexTemp/stylecam_efinity_20261004")
    (out / "efinity").mkdir(exist_ok=True)
    for filename in ("vision_map.log", "vision_map.map.out", "vision_map.res.csv", "vision_map.warn.log"):
        shutil.copy2(efx / "outflow" / filename, out / "efinity" / filename)
    shutil.copy2(efx / "sources.json", out / "efinity/sources.json")
    map_log = (efx / "outflow/vision_map.log").read_text(encoding="utf-8", errors="replace")
    assert "Stage completed: map" in map_log
    (out / "source_snapshot").mkdir(exist_ok=True)
    for filename in ("train_art_styles_v4.py", "eval_art_styles_v4.py", "art_spatial_priors.py", "audit_art_training_v6.py"):
        shutil.copy2(root / "algo" / filename, out / "source_snapshot" / filename)
    comparison = {s: {key: dict(v3=old["means"][s][key], v6=new["means"][s][key])
                       for key in old["means"][s]} for s in final["styles"]}
    (out / "comparison_200.json").write_text(json.dumps(comparison, indent=2), encoding="utf-8")
    record = dict(runs=checkpoints, selected_candidate=runs[-1], float_shape_tests=shape_tests,
                  parameters=dict(zip(("conv_weights", "norm_affine", "output_bias"), param_count(net.specs, 3))),
                  conv_macs_vga=macs*640*480, conv_macs_720p=macs*1280*720,
                  torch_version=torch.__version__, gpu=torch.cuda.get_device_name(),
                  inference_postprocessing="Only network clamp and float-to-uint8 conversion; no artistic filter",
                  quantization_ready=False, stale_activation_ranges=True,
                  deployment_headers_untouched=untouched,
                  efinity=dict(map_pass=True, stage=str(efx), rams=172, dsp=120,
                               scope="Old c24_gram vision_top subsystem; no new art weights, no SDC, no board interface",
                               full_board_timing_pass=False, board_fps_measured=False))
    (out / "audit.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    ev = root / "runs" / runs[-1] / "eval_vga_200"
    # A compact, fixed-index preview; complete saved examples remain in ev.
    sample_ids = [Path(new["records"][i]["image"]).stem for i in (8, 11, 15)]
    sheet = Image.new("RGB", (1280, 268*len(sample_ids)), "white")
    draw = ImageDraw.Draw(sheet)
    for row, stem in enumerate(sample_ids):
        for col, (suffix, label) in enumerate(zip(["input"]+final["styles"], ["Input", "Van Gogh", "Ukiyo-e", "Ink wash"])):
            im = Image.open(ev/f"{stem}_{suffix}.png").convert("RGB")
            sheet.paste(im.resize((320, 240), Image.Resampling.LANCZOS), (col*320, row*268+28))
            draw.text((col*320+5, row*268+7), label, fill="black")
    sheet.save(out / "preview_v6.jpg", quality=95)
    print(json.dumps(dict(output=str(out), parameters=record["parameters"], conv_macs_vga=record["conv_macs_vga"],
                          comparison=comparison, float_shape_tests=len(shape_tests), efinity_map_pass=True), indent=2))


if __name__ == "__main__":
    main()
