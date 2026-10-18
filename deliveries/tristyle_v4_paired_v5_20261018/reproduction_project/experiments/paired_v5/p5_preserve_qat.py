"""Formal P5 600-step preservation QAT; launch only after recorded model freeze.

Uses the saved V3 QAT implementation. The reference is the selected FP32
network, never the photo or a procedural target. Export validation is separate.
"""
from pathlib import Path
import argparse
import copy
import datetime as dt
import hashlib
import json
import random
import sys

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'diagnostics'))
from v3_access import V3, model_for_state
import quantize as qm
from consistent_qat import align_weight_fake_quant, simulate_int32_bias, input_scales_from_pack


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--checkpoint', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--freeze-record', required=True)
    a = ap.parse_args()
    owner = json.loads(Path('D:/ClaudeTest/guidance/OWNER.json').read_text(encoding='utf-8-sig'))
    assert owner['owner'] == 'codex'
    checkpoint = (ROOT / a.checkpoint).resolve()
    freeze_path = (ROOT / a.freeze_record).resolve()
    freeze = json.loads(freeze_path.read_text(encoding='utf-8-sig'))
    assert freeze['checkpoint_sha256'] == sha(checkpoint)
    assert freeze['frozen'] is True
    out = (ROOT / a.out).resolve()
    assert ROOT in out.parents and V3 not in out.parents
    out.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(3)
    torch.backends.quantized.engine = 'onednn'
    random.seed(31)
    np.random.seed(31)
    torch.manual_seed(31)
    torch.cuda.manual_seed_all(31)
    state = torch.load(checkpoint, map_location='cpu', weights_only=False)['model']
    fp = model_for_state(state).eval()
    fp.load_state_dict(state)
    qm.ROOT = V3
    qm.QAT_DIRS = ['vangogh_p1', 'ukiyoe_p1', 'ink_p1']
    sources = out / 'source'
    sources.mkdir()
    hashes = {}
    for p in [Path(__file__), Path(qm.__file__),
              ROOT/'baseline/source/claude_impl/model.py',
              ROOT/'baseline/source/claude_impl/graph.py',
              ROOT/'baseline/source/claude_impl/int_contract.py',
              ROOT/'baseline/source/claude_impl/train.py',
              Path(__file__).with_name('consistent_qat.py'),
              ROOT/'diagnostics/v3_access.py']:
        (sources / p.name).write_bytes(p.read_bytes())
        hashes[str(p)] = sha(p)
    splits = V3 / 'data/splits.json'
    paths = json.loads(splits.read_text(encoding='utf-8'))['train'][:32]
    calibration = [{'path': str(V3/p), 'sha256': sha(V3/p)} for p in paths]
    cfg = {'phase': 'P5', 'time': dt.datetime.now().astimezone().isoformat(),
           'checkpoint': str(checkpoint), 'checkpoint_sha256': sha(checkpoint),
           'freeze_record': str(freeze_path), 'freeze_record_sha256': sha(freeze_path),
           'steps': 600, 'batch': 1, 'lr': 3e-5, 'seed': 31,
           'calibration': calibration, 'splits_sha256': sha(splits),
           'robust_calibration_percentiles': [.001, .999],
           'freeze_activation': True, 'sources': hashes,
           'weight_fake_quant': 'ordinary FakeQuantize aligned to conversion observer; see P4/weight_qparam_fix_01',
           'INT32_bias_simulation': 'STE rounding in accumulator units; activation ranges frozen, no graph/parameter addition',
           'objective': 'preserve selected FP32 network; all loss terms reference its outputs',
           'legacy_loader': 'Loads old paired targets but they are unused in objective=preserve',
           'artistic_passed': False, 'integer_retention_validated': False,
           'warning': '600 steps and export completion alone are not an acceptance gate'}
    (out/'config.json').write_text(json.dumps(cfg, indent=2), encoding='utf-8')
    torch.save({'python': random.getstate(), 'numpy': np.random.get_state(),
                'torch': torch.get_rng_state(), 'cuda': torch.cuda.get_rng_state_all()}, out/'rng_start.pt')
    print('CALIBRATING_TRAIN_ONLY_32', flush=True)
    q = qm.calibrate(fp, n=32, robust=True)
    aligned = align_weight_fake_quant(q)
    assert len(aligned) == 91
    qm.pack(qm.to_int(q), fp, out/'calibration_contract.bin')
    in_scales = input_scales_from_pack(out/'calibration_contract.bin')
    (out/'input_scales.json').write_text(json.dumps(in_scales, indent=2))
    assert len(simulate_int32_bias(q, in_scales)) == 91
    (out/'calibration_bounds.json').write_text(json.dumps(q._robust_calibration_bounds, indent=2))
    torch.save(q.state_dict(), out/'calibrated_fake_int8_state.pt')
    print('P5_PRESERVE_QAT_600', flush=True)
    # Same preservation recipe as the recorded rehearsal; no photo/old-output anchor.
    q = qm._qat_from(q, fp, 600, out, dev='cuda', objective='preserve',
                     batch_size=1, freeze_activation=True)
    q.eval()
    # GPU-produced scale buffers can differ by one float32 ULP from the CPU
    # observer calculation used by convert(). Reconcile on the export device.
    align_weight_fake_quant(q)
    plain = qm.qat_to_plain(q)
    disabled = copy.deepcopy(q)
    disabled.apply(torch.ao.quantization.disable_fake_quant)
    x = torch.rand(1, 3, 48, 64)
    with torch.no_grad():
        error = max(float((plain(x, s)-disabled(x, s)).abs().max()) for s in range(3))
    assert error < 1e-4
    torch.save({'model': plain.state_dict(), 'source_checkpoint': str(checkpoint),
                'qat_steps': 600, 'kind': 'same-QAT-weight FP32'}, out/'fp32.pt')
    torch.save(q.state_dict(), out/'fake_int8_state.pt')
    integer = qm.to_int(q)
    weight_error = max(float((m.weight_fake_quant(m.weight).detach()-dict(integer.named_modules())[n].weight().dequantize()).abs().max())
                       for n,m in q.named_modules() if hasattr(m, 'weight_fake_quant'))
    assert weight_error < 1e-6, 'Fake/converted weight qparams disagree'
    size = qm.pack(integer, plain, out/'all_styles.bin')
    torch.jit.script(integer).save(str(out/'int8.ts'))
    torch.save({'python': random.getstate(), 'numpy': np.random.get_state(),
                'torch': torch.get_rng_state(), 'cuda': torch.cuda.get_rng_state_all()}, out/'rng_end.pt')
    result = {'completed': True, 'qat_steps': 600, 'same_weights_float_reload_maxabs': error,
              'fake_vs_integer_weights_maxabs': weight_error,
              'parameter_count': sum(p.numel() for p in plain.parameters()),
              'parameter_bytes_INT8weights_INT32bias': sum(p.numel()*(4 if n.endswith('bias') else 1) for n,p in plain.named_parameters()),
              'compressed_pack': size, 'integer_retention_validated': False,
              'artistic_passed': False, 'time': dt.datetime.now().astimezone().isoformat()}
    (out/'RESULT.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print('P5_QAT_EXPORT_COMPLETE_NEEDS_VALIDATION', flush=True)


if __name__ == '__main__':
    main()
