"""P4 deployment-chain rehearsal only; does not promote an artistic candidate."""
from pathlib import Path
import argparse,copy,hashlib,json,random,sys,time
import numpy as np
import torch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'diagnostics'))
from v3_access import V3,model_for_state
import quantize as qm

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--checkpoint',required=True);ap.add_argument('--out',required=True)
    ap.add_argument('--steps',type=int,default=8);ap.add_argument('--calibration',type=int,default=4);a=ap.parse_args()
    assert json.loads(Path('D:/ClaudeTest/guidance/OWNER.json').read_text(encoding='utf-8-sig'))['owner']=='codex'
    assert 0<a.steps<=16,'P4 rehearsal only; final 600-step QAT needs its own recorded stage'
    out=ROOT/a.out;out.mkdir(parents=True,exist_ok=False)
    torch.set_num_threads(3);torch.backends.quantized.engine='onednn';random.seed(31);np.random.seed(31);torch.manual_seed(31)
    checkpoint=ROOT/a.checkpoint;state=torch.load(checkpoint,map_location='cpu',weights_only=False)['model']
    fp=model_for_state(state).eval();fp.load_state_dict(state)
    qm.ROOT=V3;qm.QAT_DIRS=['vangogh_p1','ukiyoe_p1','ink_p1']
    source_dir=out/'source';source_dir.mkdir()
    for p in [Path(__file__),Path(qm.__file__),ROOT/'baseline/source/claude_impl/model.py',ROOT/'baseline/source/claude_impl/graph.py',ROOT/'baseline/source/claude_impl/int_contract.py']:
        (source_dir/p.name).write_bytes(p.read_bytes())
    cfg={'checkpoint':str(checkpoint),'checkpoint_sha256':sha(checkpoint),'steps':a.steps,'calibration_train_images':a.calibration,
         'objective':'preserve current FP32 teacher ONLY; legacy procedural targets loaded by legacy data loader are NOT optimization targets',
         'data_root_readonly':str(V3),'scope':'P4 smoke, NOT final QAT / deployment acceptance','artistic_passed':False}
    (out/'config.json').write_text(json.dumps(cfg,indent=2))
    print('CALIBRATING_TRAIN_ONLY',flush=True)
    q=qm.calibrate(fp,n=a.calibration,robust=True)
    print('PRESERVE_QAT_SMOKE',flush=True)
    q=qm._qat_from(q,fp,a.steps,out,dev='cuda',objective='preserve',batch_size=1,freeze_activation=True)
    q.eval();plain=qm.qat_to_plain(q)
    fq_disabled=copy.deepcopy(q);fq_disabled.apply(torch.ao.quantization.disable_fake_quant)
    x=torch.rand(1,3,48,64)
    with torch.no_grad():err=max(float((plain(x,s)-fq_disabled(x,s)).abs().max()) for s in range(3))
    assert err<1e-4
    integer=qm.to_int(q);size=qm.pack(integer,plain,out/'smoke_all.bin')
    ts=torch.jit.script(integer);ts.save(str(out/'smoke_int8.ts'))
    torch.save({'model':plain.state_dict(),'kind':'P4 rehearsal same-QAT-weight FP32; NOT promoted'},out/'smoke_fp32.pt')
    torch.save(q.state_dict(),out/'smoke_fake_int8_state.pt')
    with torch.no_grad():
        errors=[float((q(x,s)-ts(x,s)).abs().max()) for s in range(3)]
    result={'smoke_completed':True,'qat_steps':a.steps,'float_vs_fake_disabled_maxabs':err,'fake_vs_onednn_random_maxabs':errors,
            'pack':size,'parameter_count':sum(p.numel() for p in plain.parameters()),
            'parameter_bytes_planned_INT8weights_INT32bias':sum(p.numel()*(4 if n.endswith('bias') else 1) for n,p in plain.named_parameters()),
            'limitations':'4 training-image calibration / 8-step default rehearsal; not full600 QAT, fixed17 validation, normative integer execution, art acceptance, RTL/synthesis or board fps.'}
    (out/'RESULT.json').write_text(json.dumps(result,indent=2));print('QAT_REHEARSAL_COMPLETE',json.dumps(result),flush=True)

if __name__=='__main__':main()
