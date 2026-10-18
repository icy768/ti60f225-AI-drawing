"""Write final_index.md from actual artifacts on disk (reads JSON outputs; no hand-typed numbers).
Usage: final_index.py <deployment_dir> <selected_ckpt> <video_fp32_dir> <video_int8_dir> <visual_verdict.json>"""
import sys, json, pathlib, time, hashlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
def L(p): return f'[{p}]({p})' if (ROOT / p).exists() else f'{p} (MISSING)'
def J(p):
    try: return json.loads((ROOT / p).read_text(encoding='utf-8'))
    except Exception: return None

def main():
    dep, ck, vf, vi, verdict = sys.argv[1:6]
    pb = J(f'{dep}/pack_bytes.json'); qm = J(f'{dep}/quantization_metrics.json'); ir = J(f'{dep}/int_ref_verification.json')
    vfm = J(f'{vf}/video_fp32_metrics.json'); vim = J(f'{vi}/video_int8_metrics.json'); vd = J(verdict) or {}
    hw = 'reports/claude/HARDWARE_V3.md'
    o = ['# Tri-style first delivery (Claude implementation) - index', '',
         f"Generated {time.strftime('%Y-%m-%d %H:%M:%S')} Asia/Shanghai from files on disk. Implementation owner: Claude Code (claude_impl/); supervision: Codex (SUPERVISOR_FEEDBACK.md).", '',
         '## Acceptance status (honest)', '']
    for k, v in vd.get('styles', {}).items(): o.append(f'- **{k}**: {v}')
    for x in vd.get('limitations', []): o.append(f'- {x}')
    o += ['', '## Selected model', '', f'- Selected training checkpoint: {L(ck)} ({vd.get("selection_reason", "")})',
          f'- Delivered float weights (same weights as INT8 pack): {L(dep + "/tristyle_v3_fp32.pt")}  (load: `TriStyleV3().load_state_dict(torch.load(p)["model"])`)',
          f'- Pre-QAT art baseline: {L(dep + "/pre_qat_fp32.pt")}',
          f'- INT8 all-style deployment pack: {L(dep + "/tristyle_v3_all.bin")}', f'- Host INT8 executable (TorchScript, oneDNN): {L(dep + "/tristyle_v3_int8.ts")}', '']
    if pb: o += [f"Pack size **{pb['total_bytes']} bytes** (limit 500000, fits={pb['fits']}): weights {pb['weight_int8']}, INT32 bias {pb['bias_int32']}, Q31 multipliers {pb['multiplier_int32']}, exponents {pb['exponent_int8']}, zlib metadata+graph {pb['metadata_zlib']}, header {pb['header']}. Per part: {pb['per_part']}. sha256 {pb['sha256']}.", '']
    o += ['## Visual evidence (fixed 17 test scenes, never used for training)', '',
          f'- All 17 scenes x 3 styles, FP32 (native resolution): {L(dep + "/all17_three_styles_fp32.jpg")}', f'- Same, INT8 TorchScript: {L(dep + "/all17_three_styles_int8.jpg")}',
          f'- Individual PNGs: {L(dep + "/gallery")}', f'- FP32 vs INT8 at 320x240: {L(dep + "/int8_comparison.jpg")}',
          f'- Training progress galleries per 1000 steps: {L("reports/claude/progress")}', f'- Inspection crops used in reviews: {L("reports/claude/inspect")}',
          f'- TARGET previews (training guidance, NOT student output): {L("reports/claude/guides_v9_targets.jpg")}, {L("reports/claude/guides_v8_targets.jpg")}', '']
    o += ['## Quantisation', '']
    if qm: o += [f"- {qm.get('float_reference')}; QAT steps {qm.get('qat_steps')}. Mean FP32-vs-INT8 over 17 scenes @320x240: " + ', '.join(f"{s} PSNR {v['fp32_vs_int8_PSNR']:.1f} dB / SSIM {v['fp32_vs_int8_SSIM']:.3f}" for s, v in qm['summary'].items()) + f" ({L(dep + '/quantization_metrics.json')})"]
    if ir: o += [f"- Pack-only integer interpreter (claude_impl/int_ref.py, int64 conv, Q31 RNE) vs oneDNN TorchScript: real images max {ir.get('max_LSB_REAL_IMAGES')} LSB, PSNR {ir.get('mean_PSNR_intref_vs_onednn_REAL_IMAGES', 0):.1f} dB; int_ref vs FP32 {ir.get('mean_PSNR_intref_vs_fp32_REAL_IMAGES', 0):.1f} dB; max INT32 accumulator {ir.get('max_int_accumulator')} ({L(dep + '/int_ref_verification.json')}). NOT bit-exact between backends (tie-rounding differences, traced per op).", '']
    o += ['## Real video (Sintel trailer, CC BY 3.0)', '']
    for tag, m, d in (('FP32', vfm, vf), ('INT8', vim, vi)):
        if m:
            s = m['summary']; o.append(f"- {tag}: held-out frames {s['heldout_start_frame']}+ ({s['frames']} frames, {s['size'][0]}x{s['size'][1]}); input warp MAE {s['input_warp_MAE_mean']:.4f}; styled warp MAE " + ', '.join(f"{k} {s[k]['warp_MAE_mean']:.4f}" for k in ('vangogh', 'ukiyoe', 'ink')) + f" - video {L(d + '/heldout_' + tag.lower() + '.mp4')}, metrics {L(d + '/video_' + tag.lower() + '_metrics.json')}")
    o += ['- Held-out rule: training pairs use frames 63-624 only; frames >= 640 are unseen. The original evaluation start (1013) is title card/credits only, also reported in reports/claude/video_v3c3000.', '',
          '## Hardware (parameterised estimate, NOT measured)', '', f'- {L(hw)} and {L("reports/claude/hardware_v3.json")} - DDR3 MT41J128M16JT-125 per HARDWARE_INPUT.md; supersedes the obsolete HyperRAM reports/HARDWARE.md.',
          '- Conclusion: 640x480 >= 15 fps NOT reachable with this network under 1 INT8 MAC/DSP/cycle; 320x240 reduced-resolution mode estimate only. No Efinity synthesis/P&R/RTL/board run performed.', '',
          '## Code, reproduction, provenance', '',
          f'- Implementation: {L("claude_impl")} (model.py, guides*.py, precompute*.py, train.py, quantize.py, graph.py, int_ref.py, video_eval.py, hardware.py, deliver.py, manifest.py)',
          f'- Run logs/configs/source snapshots: {L("runs")}/claude_v3a, claude_v3b, claude_v3c, claude_v3d (+ claude_v3e if present); each has config.json, provenance.json, metrics.jsonl, train*.log, source/',
          f'- Manifest (environment, source/checkpoint/deployment sha256, data/licence): {L(dep + "/MANIFEST.json")}', f'- Supervisor status trail: {L("supervisor/claude_status.json")}', '',
          '### Commands', '', '```', 'PY=C:/Users/<user>/AppData/Local/Programs/Python/Python310/python.exe   # torch 2.7.1+cu118',
          '$PY claude_impl/precompute.py train --vg ; $PY claude_impl/precompute.py train ; $PY claude_impl/precompute.py train --v2   # targets (+ validation)',
          '$PY claude_impl/precompute3.py train 0 1 ; $PY claude_impl/precompute4.py train 0 1 ; $PY claude_impl/precompute5.py train 0 1',
          '$PY claude_impl/train.py --run <name> ...   # exact args per run in runs/<run>/config.json',
          f'CUDA_VISIBLE_DEVICES= $PY claude_impl/quantize.py --checkpoint {ck} --out {dep} --qat-steps N --device cpu --targets vangogh5,ukiyoe2,ink34',
          f'$PY claude_impl/int_ref.py {dep} ; $PY claude_impl/deliver.py {dep} {ck} run ; $PY claude_impl/video_eval.py --checkpoint {dep}/tristyle_v3_fp32.pt --out {vf} --start 640',
          f'$PY claude_impl/video_eval.py --ts {dep}/tristyle_v3_int8.ts --out {vi} --start 640 ; $PY claude_impl/hardware.py {dep}/pack_bytes.json ; $PY claude_impl/manifest.py {dep} {ck}', '```']
    (ROOT / 'final_index.md').write_text('\n'.join(o), encoding='utf-8'); print('\n'.join(o[:30]))

if __name__ == '__main__':
    main()
