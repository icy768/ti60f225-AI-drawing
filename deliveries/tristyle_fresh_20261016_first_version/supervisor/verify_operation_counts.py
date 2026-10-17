"""Independent torch forward-hook count vs serialized-graph dimension arithmetic."""
import argparse,json,pathlib,sys,torch
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'claude_impl'));sys.path.insert(1,str(ROOT/'continuation_impl'))
from model import model_for_state,STYLES
from int_ref import IntGraph
from hardware_final import count
ap=argparse.ArgumentParser();ap.add_argument('deployment');a=ap.parse_args();dep=ROOT/a.deployment
torch.set_num_threads(2);state=torch.load(dep/'tristyle_v3_fp32.pt',map_location='cpu',weights_only=False)['model']
m=model_for_state(state).eval();m.load_state_dict(state);g=IntGraph(dep/'tristyle_v3_hw.bin');rows=[]
for s,name in enumerate(STYLES):
    total=[0];hooks=[]
    for mod in m.modules():
        if isinstance(mod,torch.nn.Conv2d):
            def hook(mod,args,out):total[0]+=out.numel()*(mod.in_channels//mod.groups)*mod.kernel_size[0]*mod.kernel_size[1]
            hooks.append(mod.register_forward_hook(hook))
    with torch.inference_mode():m(torch.zeros(1,3,64,80),s)
    for h in hooks:h.remove()
    graph=count(g,s,640,480)['MAC'];assert total[0]*60==graph,(name,total[0]*60,graph)
    rows.append({'style':name,'torch_hook_MAC_80x64':total[0],'linear_area_scale':60,'graph_MAC_640x480':graph,'equal':True})
result={'status':'MEASURED torch shape/hooks agree exactly with serialized-graph arithmetic',
    'scope':'MAC counts only; no FPGA resource, cycle or throughput validation','rows':rows}
(dep/'operation_count_verification.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
