"""Recover inference-only gallery from saved checkpoint, without training."""
import json
import sys
from pathlib import Path
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'experiments'))
sys.path.insert(0, str(ROOT/'diagnostics'))
from model_v4_direct import DirectLiteV4
from v3_access import model_for_state
from style_pilot import gallery

torch.set_num_threads(3)
ck = torch.load(ROOT/'experiments/pilot_decoder_direct_01/step_002400.pt', map_location='cpu', weights_only=False)
m = DirectLiteV4().cuda().eval()
m.load_state_dict(ck['model'])
s = torch.load(ROOT/'baseline/tristyle_v3_fp32.pt', map_location='cpu', weights_only=False)['model']
v3 = model_for_state(s).cuda().eval()
v3.load_state_dict(s)
gallery(m, v3, ROOT/'reports/pilot_decoder_direct_01/002400', 'cuda', 2400)
(ROOT/'experiments/pilot_decoder_direct_01/interruption_record.json').write_text(json.dumps({
    'last_saved_step': 2400, 'planned_steps': ck['config']['steps'], 'pid_4836_exists': False,
    'error_log_bytes': (ROOT/'logs/pilot_decoder_direct_01.err.log').stat().st_size,
    'partial_gallery_png_before_recovery': 70,
    'exit_cause': 'Unknown. Process absent, no Python traceback. Do not assert CUDA failure.',
    'action': 'Inference-only recovery at saved step2400; no training resumed. Quality rejection pending full review.',
    'finished_json': 'Not synthesized; run did not reach planned final step.'}, indent=2))
print('Recovered full saved17 inference gallery; no training.')
