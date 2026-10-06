"""Capture one real webcam sequence and compare identical frames across checkpoints.

This is a PC camera diagnostic, not SC431HAI or FPGA validation.
"""
import argparse
import hashlib
import json
import shutil
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw
import torch

from tinystyle import QCfg, TinyStyleNet
from train import ROOT


def aligned_error(previous, current, flow, valid):
    height, width = previous.shape[:2]
    xx, yy = np.meshgrid(np.arange(width), np.arange(height))
    mx = (xx + flow[..., 0]).astype(np.float32)
    my = (yy + flow[..., 1]).astype(np.float32)
    warped = cv2.remap(current, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    error = np.abs(previous.astype(np.float32) - warped.astype(np.float32)).mean(2)
    return float(error[valid].mean()) if valid.any() else None, float(valid.mean())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--models', nargs='+', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--camera', type=int, default=0)
    parser.add_argument('--frames', type=int, default=30)
    parser.add_argument('--frames-dir', help='Replay saved raw frames from a real camera capture')
    args = parser.parse_args()
    root = Path(ROOT)
    out = root / args.out
    out.mkdir(parents=True, exist_ok=False)
    raw = out / 'raw'
    raw.mkdir()
    frames, stamps = [], []
    if args.frames_dir:
        source = Path(args.frames_dir)
        captures = sorted(source.glob('*.png'))
        if len(captures) != args.frames:
            raise ValueError(f'Expected {args.frames} saved frames, found {len(captures)}')
        capture_report = json.loads((source.parent / 'summary.json').read_text(encoding='utf-8'))
        stamps = capture_report['capture_timestamps_monotonic_ns']
        if len(stamps) != len(captures):
            raise ValueError('Capture timestamps do not match frame count')
        for index, path in enumerate(captures):
            rgb = np.asarray(Image.open(path).convert('RGB'))
            if rgb.shape != (480, 640, 3):
                raise ValueError(f'Unexpected saved frame: {path}')
            if hashlib.sha256(rgb.tobytes()).hexdigest() != capture_report['frame_sha256'][index]:
                raise ValueError(f'Capture hash mismatch: {path}')
            frames.append(rgb)
            shutil.copy2(path, raw / f'{index:03}.png')
    else:
        cap = cv2.VideoCapture(args.camera, cv2.CAP_DSHOW)
        if not cap.isOpened():
            raise RuntimeError(f'Camera {args.camera} could not open')
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, 30)
        try:
            for index in range(args.frames):
                ok, bgr = cap.read()
                stamp = time.monotonic_ns()
                if not ok or bgr is None:
                    raise RuntimeError(f'Camera read failed at frame {index}')
                if bgr.shape[:2] != (480, 640):
                    raise RuntimeError(f'Unexpected camera frame: {bgr.shape}')
                rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                frames.append(rgb)
                stamps.append(stamp)
                Image.fromarray(rgb).save(raw / f'{index:03}.png')
        finally:
            cap.release()
    hashes = [hashlib.sha256(x.tobytes()).hexdigest() for x in frames]
    cadence = np.diff(np.asarray(stamps, dtype=np.float64)) / 1e9
    input_delta = [float(np.abs(a.astype(np.float32) - b).mean()) for a, b in zip(frames[:-1], frames[1:])]
    flows = [cv2.calcOpticalFlowFarneback(cv2.cvtColor(a, cv2.COLOR_RGB2GRAY),
                                         cv2.cvtColor(b, cv2.COLOR_RGB2GRAY),
                                         None, .5, 3, 15, 3, 5, 1.2, 0)
             for a, b in zip(frames[:-1], frames[1:])]
    xx, yy = np.meshgrid(np.arange(640), np.arange(480))
    masks = []
    for a, b, flow in zip(frames[:-1], frames[1:], flows):
        mx, my = (xx + flow[..., 0]).astype(np.float32), (yy + flow[..., 1]).astype(np.float32)
        warped = cv2.remap(b, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        masks.append(((xx >= 20) & (xx < 620) & (yy >= 20) & (yy < 460) &
                      (mx >= 20) & (mx < 620) & (my >= 20) & (my < 460) &
                      (np.linalg.norm(flow, axis=2) < 16) &
                      (np.abs(a.astype(np.float32) - warped.astype(np.float32)).mean(2) < 30)))
    torch.set_num_threads(4)
    QCfg.enabled = QCfg.observe = False
    report = dict(camera_index=args.camera, camera_kind='PC USB camera; not SC431HAI',
                  inference_kind='FP32 CUDA; not FPGA', frame_count=len(frames),
                  replayed_from=str(args.frames_dir) if args.frames_dir else None,
                  image_size=[640, 480], frame_sha256=hashes,
                  capture_timestamps_monotonic_ns=stamps,
                  capture_elapsed_s=(stamps[-1] - stamps[0]) / 1e9,
                  capture_interval_ms=dict(mean=float(cadence.mean() * 1000),
                                           p95=float(np.percentile(cadence, 95) * 1000)),
                  unique_frames=len(set(hashes)), input_delta_255=float(np.mean(input_delta)),
                  models={})
    sample_indices = sorted({0, len(frames) // 2, len(frames) - 1})
    for checkpoint in args.models:
        path = root / checkpoint
        ck = torch.load(path, map_location='cpu', weights_only=False)
        net = TinyStyleNet(**ck['cfg']).cuda().eval()
        net.load_state_dict(ck['sd'])
        name = path.parent.name
        dest = out / name
        dest.mkdir()
        model = dict(checkpoint=checkpoint, sha256=hashlib.sha256(path.read_bytes()).hexdigest(), styles={})
        for style_index, style in enumerate(ck['styles']):
            outputs, latencies = [], []
            with torch.no_grad():
                st = torch.tensor([style_index], device='cuda')
                for index, rgb in enumerate(frames):
                    x = torch.from_numpy(rgb.copy()).permute(2, 0, 1)[None].cuda().float() / 255
                    torch.cuda.synchronize()
                    start = time.perf_counter()
                    y = net(x, st)
                    torch.cuda.synchronize()
                    latencies.append((time.perf_counter() - start) * 1000)
                    result = (y[0].permute(1, 2, 0).cpu().numpy() * 255).round().clip(0, 255).astype(np.uint8)
                    outputs.append(result)
                    if index in sample_indices:
                        Image.fromarray(result).save(dest / f'{index:03}_{style}.png')
            aligned, valid = zip(*(aligned_error(a, b, flow, mask) for a, b, flow, mask in
                                    zip(outputs[:-1], outputs[1:], flows, masks)))
            model['styles'][style] = dict(aligned_mae_255=float(np.mean([v for v in aligned if v is not None])),
                                          mean_valid_fraction=float(np.mean(valid)),
                                          raw_delta_255=float(np.mean([
                                              np.abs(a.astype(np.float32) - b).mean()
                                              for a, b in zip(outputs[:-1], outputs[1:])])),
                                          pc_cuda_latency_ms_median=float(np.median(latencies)))
        report['models'][name] = model
        print(name, json.dumps(model['styles']), flush=True)
    names = list(report['models'])
    for index in sample_indices:
        for style in next(iter(report['models'].values()))['styles']:
            sheet = Image.new('RGB', (320 * (len(names) + 1), 270), 'white')
            draw = ImageDraw.Draw(sheet)
            for column, image in enumerate([raw / f'{index:03}.png'] +
                                           [out / name / f'{index:03}_{style}.png' for name in names]):
                sheet.paste(Image.open(image).resize((320, 240)), (320 * column, 30))
                draw.text((320 * column + 4, 6), 'input' if column == 0 else names[column - 1], fill='black')
            sheet.save(out / f'comparison_{index:03}_{style}.jpg', quality=94)
    (out / 'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('SAVED', out, flush=True)


if __name__ == '__main__':
    main()
