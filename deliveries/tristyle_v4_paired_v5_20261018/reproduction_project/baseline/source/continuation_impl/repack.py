"""Repack an existing completed QAT artifact without retraining or changing its weights."""
import argparse, hashlib, json, pathlib, shutil, sys
import torch
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'claude_impl'))
from model import TriStyleV3, model_for_state
from quantize import prepared, to_int, pack


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--source', required=True); ap.add_argument('--out', required=True)
    a = ap.parse_args(); source = ROOT / a.source; out = ROOT / a.out; out.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(3); torch.backends.quantized.engine = 'onednn'
    state = torch.load(source / 'tristyle_v3_fp32.pt', map_location='cpu', weights_only=False)['model']
    fp = model_for_state(state).eval(); fp.load_state_dict(state)
    q = prepared(fp); q.load_state_dict(torch.load(source / 'fake_int8_state.pt', map_location='cpu', weights_only=False), strict=True); q.eval()
    qi = to_int(q); report = pack(qi, fp, out / 'tristyle_v3_all.bin')
    assert report['fits'], report
    torch.jit.script(qi).save(str(out / 'tristyle_v3_int8.ts'))
    for name in ('tristyle_v3_fp32.pt', 'pre_qat_fp32.pt', 'fake_int8_state.pt', 'quantization_metrics.json', 'qat_metrics.jsonl', 'export_config.json'):
        if (source / name).exists(): shutil.copy2(source / name, out / name)
    (out / 'pack_bytes.json').write_text(json.dumps(report, indent=2))
    (out / 'repack_provenance.json').write_text(json.dumps({'source': a.source, 'mode': 'saved QAT state reloaded; no additional training',
        'source_bin_sha256': hashlib.sha256((source / 'tristyle_v3_all.bin').read_bytes()).hexdigest(),
        'fp32_sha256': hashlib.sha256((out / 'tristyle_v3_fp32.pt').read_bytes()).hexdigest(),
        'changes': 'serialized integer input/add/cat/output constants and conservative accumulator bounds; float scales diagnostic only'}, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__': main()
