"""CPU tensor-operation counts, not synthesis or measured FPGA throughput."""
from pathlib import Path
import json,sys
import torch
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(Path(__file__).parent))
from fit_capacity import model_for_state,apply_architecture,sha,now

def main():
    torch.set_num_threads(3);p=ROOT/'baseline/tristyle_v3_fp32.pt';state=torch.load(p,map_location='cpu',weights_only=False)['model'];records=[]
    for dilated in (False,True):
        m=model_for_state(state).eval();m.load_state_dict(state);apply_architecture(m,dilated)
        for h,w in ((240,320),(480,640)):
            for style in ([1] if dilated else [0,1,2]):
                layers=[];handles=[]
                for name,mod in m.named_modules():
                    if not isinstance(mod,torch.nn.Conv2d):continue
                    def hook(layer,ins,out,n=name):
                        x=ins[0];kh,kw=layer.kernel_size;dh,dw=layer.dilation
                        layers.append({'layer':n,'input':list(x.shape),'output':list(out.shape),'kernel':[kh,kw],'dilation':[dh,dw],'groups':layer.groups,'MAC':out.numel()*(layer.in_channels//layer.groups)*kh*kw,'naive_INT8_vertical_linebuffer_bytes':(kh-1)*dh*x.shape[-1]*layer.in_channels,'horizontal_reach_pixels':(kw-1)*dw+1,'naive_all_activation_RW_bytes':x.numel()+out.numel()})
                    handles.append(mod.register_forward_hook(hook))
                with torch.no_grad():m(torch.zeros(1,3,h,w),style)
                for handle in handles:handle.remove()
                records.append({'graph':'expert1_s8_dilation2' if dilated else 'V3_frozen','height':h,'width':w,'selected_style':style,'MAC_per_frame':sum(z['MAC'] for z in layers),'naive_streaming_linebuffer_sum_INT8_B':sum(z['naive_INT8_vertical_linebuffer_bytes'] for z in layers),'largest_single_linebuffer_INT8_B':max(z['naive_INT8_vertical_linebuffer_bytes'] for z in layers),'naive_external_eachconv_activation_RW_B':sum(z['naive_all_activation_RW_bytes'] for z in layers),'layers':layers})
    out=ROOT/'reports/paired_v5/P1b/context_cost_01';out.mkdir(parents=True,exist_ok=True)
    data={'time':now(),'source_sha256':sha(__file__),'checkpoint_sha256':sha(p),'parameters_all_three_styles':sum(x.numel() for x in m.parameters()),'parameter_INT8weight_INT32bias_B':sum(x.numel()*(4 if n.endswith('bias') else 1) for n,x in m.named_parameters()),'model_integer_exported':False,'FPGA_synthesis':False,'board_FPS_measured':False,'assumptions':['MAC counted by actual tensor-shape hooks; one selected style per frame, all3 styles included in parameter storage','INT8 activation assumption only, not an implemented integer schedule','Linebuffer metric sums effective kernel-height-1 input rows at every conv if all layers stream concurrently. Not a chosen architecture, lower bound or actual BRAM allocation; excludes horizontal FIFOs, alignment, primitive packing, skip lifetimes and IO','Naive external traffic reads/writes every conv activation, no reuse; omits add/concat/upsample traffic and weights. It is a schedule diagnostic, neither achievable optimized traffic nor a universal worst-case bound','Dilation changes linebuffer reach despite identical parameter/MAC/activation tensor shapes. DDR/controller efficiency and actual throughput remain unverified','320x240 internal2x output is reduced-resolution mode; upsample and camera/display overhead not in CNN conv MAC count'],'records':records}
    (out/'result.json').write_text(json.dumps(data,indent=2));print(json.dumps([{k:v for k,v in z.items() if k!='layers'} for z in records]))
if __name__=='__main__':main()
