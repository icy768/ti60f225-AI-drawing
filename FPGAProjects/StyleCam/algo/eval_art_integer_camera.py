"""Replay a saved 640x480 camera sequence through the integer golden model."""
import argparse
import hashlib
import json
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

import golden
from train import ROOT


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--qparams", required=True)
    p.add_argument("--frames-dir", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--frames", type=int, default=30)
    args = p.parse_args()
    root = Path(ROOT)
    out = root / args.out
    out.mkdir(parents=True, exist_ok=False)
    q = golden.load(str(root / args.qparams))
    paths = sorted((root / args.frames_dir).glob("*.png"))
    if len(paths) != args.frames:
        raise ValueError(f"expected {args.frames} frames, found {len(paths)}")
    frames = [np.asarray(Image.open(f).convert("RGB")) for f in paths]
    if any(x.shape != (480, 640, 3) for x in frames):
        raise ValueError("all frames must be 640x480 RGB")
    report = {"qparams": args.qparams, "qparams_sha256": hashlib.sha256((root / (args.qparams + ".json")).read_bytes()).hexdigest(),
              "frames_dir": args.frames_dir, "frame_count": len(frames), "styles": q["styles"], "models": {}}
    xx, yy = np.meshgrid(np.arange(640), np.arange(480))
    flows = []
    masks = []
    for a, b in zip(frames[:-1], frames[1:]):
        flow = cv2.calcOpticalFlowFarneback(cv2.cvtColor(a, cv2.COLOR_RGB2GRAY),
                                            cv2.cvtColor(b, cv2.COLOR_RGB2GRAY),
                                            None, .5, 3, 15, 3, 5, 1.2, 0)
        mx, my = (xx + flow[..., 0]).astype(np.float32), (yy + flow[..., 1]).astype(np.float32)
        warped = cv2.remap(b, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        mask = ((xx >= 20) & (xx < 620) & (yy >= 20) & (yy < 460) &
                (mx >= 20) & (mx < 620) & (my >= 20) & (my < 460) &
                (np.linalg.norm(flow, axis=2) < 16) &
                (np.abs(a.astype(np.float32) - warped).mean(2) < 30))
        flows.append(flow); masks.append(mask)
    for si, style in enumerate(q["styles"]):
        outputs, elapsed = [], []
        for frame in frames:
            start = time.perf_counter()
            y, _, _ = golden.run(q, frame, si)
            elapsed.append((time.perf_counter() - start) * 1000)
            outputs.append(y)
        aligned, valid, raw = [], [], []
        for a, b, flow, mask in zip(outputs[:-1], outputs[1:], flows, masks):
            mx, my = (xx + flow[..., 0]).astype(np.float32), (yy + flow[..., 1]).astype(np.float32)
            warped = cv2.remap(b, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
            aligned.append(float(np.abs(a.astype(np.float32) - warped).mean(2)[mask].mean()))
            valid.append(float(mask.mean()))
            raw.append(float(np.abs(a.astype(np.float32) - b.astype(np.float32)).mean()))
        dest = out / style
        dest.mkdir()
        for idx in (0, len(outputs) // 2, len(outputs) - 1):
            Image.fromarray(outputs[idx]).save(dest / f"{idx:03}_{style}.png")
        report["models"][style] = {"aligned_mae_255": float(np.mean(aligned)),
                                    "mean_valid_fraction": float(np.mean(valid)),
                                    "raw_delta_255": float(np.mean(raw)),
                                    "golden_cpu_latency_ms_median": float(np.median(elapsed))}
        print(style, json.dumps(report["models"][style]), flush=True)
    (out / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("SAVED", out, flush=True)


if __name__ == "__main__":
    main()
