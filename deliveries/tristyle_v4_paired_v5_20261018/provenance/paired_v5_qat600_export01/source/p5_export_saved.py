"""Recover export from completed QAT600 state; never retrain or alter FP weights."""
from pathlib import Path
import copy
import hashlib
import json
import sys
import torch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'diagnostics'))
from v3_access import model_for_state
import quantize as qm
from hwpack import write_hw
from consistent_qat import align_weight_fake_quant,simulate_int32_bias


def main():
    assert json.loads(Path('D:/ClaudeTest/guidance/OWNER.json').read_text(encoding='utf-8-sig'))['owner']=='codex'
    torch.set_num_threads(3);torch.backends.quantized.engine='onednn'
    source=ROOT/'deployment/paired_v5_qat600_01'
    out=ROOT/'deployment/paired_v5_qat600_export01';out.mkdir(exist_ok=False)
    log=[json.loads(x) for x in (source/'qat_metrics.jsonl').read_text().splitlines()]
    assert log[-1]['step']==600
    ck=torch.load(source/'fp32.pt',weights_only=False,map_location='cpu')['model']
    plain=model_for_state(ck).eval();plain.load_state_dict(ck)
    q=qm.prepared(model_for_state(ck));align_weight_fake_quant(q)
    q.load_state_dict(torch.load(source/'fake_int8_state.pt',weights_only=True));q.eval()
    q.apply(torch.ao.quantization.disable_observer)
    before={n:m.weight_fake_quant.scale.clone() for n,m in q.named_modules() if hasattr(m,'weight_fake_quant')}
    align_weight_fake_quant(q) # recalculate cached scales on CPU, as convert() does
    scale_delta=max(float((before[n]-m.weight_fake_quant.scale).abs().max()) for n,m in q.named_modules() if n in before)
    simulate_int32_bias(q,json.loads((source/'input_scales.json').read_text()))
    integer=qm.to_int(q)
    error=max(float((m.weight_fake_quant(m.weight).detach()-dict(integer.named_modules())[n].weight().dequantize()).abs().max())
              for n,m in q.named_modules() if hasattr(m,'weight_fake_quant'))
    assert error<1e-6
    disabled=copy.deepcopy(q);disabled.apply(torch.ao.quantization.disable_fake_quant)
    x=torch.rand(1,3,32,40)
    with torch.no_grad():float_error=max(float((plain(x,s)-disabled(x,s)).abs().max()) for s in range(3))
    assert float_error<1e-4
    pack=qm.pack(integer,plain,out/'all_styles.bin')
    torch.jit.script(integer).save(str(out/'int8.ts'))
    torch.save(q.state_dict(),out/'fake_int8_state.pt')
    for name in ['fp32.pt','input_scales.json','calibration_bounds.json']:(out/name).write_bytes((source/name).read_bytes())
    hw=write_hw(out/'all_styles.bin',out/'all_styles_hw.bin',320,240)
    (out/'hardware_pack_bytes.json').write_text(json.dumps(hw,indent=2))
    (out/'config.json').write_text(json.dumps({'source_training_run':str(source),'qat_steps':600,
        'recovery':'CPU observer scale-cache reconciliation after GPU QAT; no retraining or FP parameter changes',
        'source_fake_sha256':hashlib.sha256((source/'fake_int8_state.pt').read_bytes()).hexdigest(),
        'source_fp32_sha256':hashlib.sha256((source/'fp32.pt').read_bytes()).hexdigest(),
        'original_config_sha256':hashlib.sha256((source/'config.json').read_bytes()).hexdigest()},indent=2))
    (out/'source').mkdir()
    for p in [Path(__file__),Path(__file__).with_name('consistent_qat.py')]: (out/'source'/p.name).write_bytes(p.read_bytes())
    result={'completed':True,'qat_steps':600,'additional_training_steps':0,'CPU_scale_reconciliation_maxabs':scale_delta,
        'fake_vs_integer_weights_maxabs':error,'same_weights_float_reload_maxabs':float_error,
        'parameter_count':sum(p.numel() for p in plain.parameters()),
        'parameter_bytes_INT8weights_INT32bias':sum(p.numel()*(4 if n.endswith('bias') else 1) for n,p in plain.named_parameters()),
        'compressed_pack':pack,'complete_fixed_package_bytes':hw['total_bytes'],'artistic_passed':False,'integer_retention_validated':False}
    (out/'RESULT.json').write_text(json.dumps(result,indent=2))
    print(json.dumps({k:v for k,v in result.items() if k!='compressed_pack'}),flush=True)


if __name__=='__main__':main()
