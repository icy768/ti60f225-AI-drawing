"""Calibrated fake INT8, executable integer TorchScript, and complete deployment pack.

The single binary contains ALL three experts, shared weights, INT32 biases,
per-output weight scales, INT32 requant multipliers/int8 exponents and metadata.
TorchScript is a host-side executable; its archive overhead is not FPGA weight RAM.
"""
import argparse,copy,json,struct,zlib,hashlib,pathlib,time,warnings
import torch,numpy as np
from torch.ao.quantization import prepare_qat,convert,FakeQuantize,QConfig,MovingAverageMinMaxObserver,default_per_channel_weight_fake_quant,disable_observer
from torch import nn
from model import TriStyle,STYLES
from data import ROOT,image_tensor

def config():
    return QConfig(activation=FakeQuantize.with_args(observer=MovingAverageMinMaxObserver,quant_min=0,quant_max=255,dtype=torch.quint8,qscheme=torch.per_tensor_affine),weight=default_per_channel_weight_fake_quant)
def make_prepared(fp):
    q=copy.deepcopy(fp).cpu().train();q.qconfig=config();prepare_qat(q,inplace=True);return q
def pack(q,path,example):
    inputs={};handles=[]
    for name,m in q.named_modules():
        if isinstance(m,torch.ao.nn.quantized.Conv2d):
            def hook(mod,args,out,key=name):inputs[key]=(float(args[0].q_scale()),int(args[0].q_zero_point()))
            handles.append(m.register_forward_hook(hook))
    with torch.inference_mode():
        for s in range(3):q(example,s)
    for h in handles:h.remove()
    payload=bytearray();manifest={'format':'TRISTYLE_INT8_V1','styles':list(STYLES),'convs':[],'scalar_state':{},'bias':'round_to_even(real_bias / input_scale / weight_scale), int32','requant':'frexp ratio = multiplier_q31 * 2**exponent / 2**31; round only once after accumulation; saturation u8','endianness':'little','torch_input':'float RGB 0..1; input Quantize is host-boundary conversion','no_runtime_normalization':True}
    totals={'weight_int8':0,'bias_int32':0,'weight_scale_fp32':0,'requant_multiplier_int32':0,'requant_exponent_int8':0}
    def put(a,cat):
        raw=a.tobytes();off=len(payload);payload.extend(raw);totals[cat]+=len(raw);return [off,len(raw)]
    for name,m in q.named_modules():
        if not isinstance(m,torch.ao.nn.quantized.Conv2d):continue
        w=m.weight();assert w.qscheme() in [torch.per_channel_affine,torch.per_channel_symmetric]
        assert (w.q_per_channel_zero_points()==0).all(),'only symmetric per-channel weights supported'
        ws=w.q_per_channel_scales().cpu().numpy().astype('<f4');ins,inz=inputs[name];outs=float(m.scale);outz=int(m.zero_point)
        bias=m.bias().detach().cpu().numpy();bi64=np.rint(bias/(ins*ws)).astype(np.int64)
        if np.abs(bi64).max()>2**31-1:raise OverflowError(name+' INT32 bias')
        frac,exp=np.frexp(ins*ws.astype(np.float64)/outs);mult=np.rint(frac*2**31).astype(np.int64)
        overflow=mult==2**31;mult[overflow]//=2;exp[overflow]+=1
        if np.abs(exp).max()>127:raise OverflowError(name+' exponent')
        desc={'name':name,'shape':list(w.shape),'stride':list(m.stride),'padding':list(m.padding),'groups':m.groups,'dilation':list(m.dilation),'input_scale':ins,'input_zp':inz,'output_scale':outs,'output_zp':outz}
        desc['weight']=put(w.int_repr().cpu().numpy().astype('i1'),'weight_int8');desc['bias']=put(bi64.astype('<i4'),'bias_int32');desc['weight_scale']=put(ws,'weight_scale_fp32');desc['multiplier']=put(mult.astype('<i4'),'requant_multiplier_int32');desc['exponent']=put(exp.astype('i1'),'requant_exponent_int8');manifest['convs'].append(desc)
    for k,v in q.state_dict().items():
        if k.endswith('.scale') or k.endswith('.zero_point'):
            if '.conv.' not in k:manifest['scalar_state'][k]=v.detach().cpu().reshape(-1).tolist()
    from graph_spec import graph_spec
    manifest['graph']=graph_spec(TriStyle())
    metadata=zlib.compress(json.dumps(manifest,separators=(',',':')).encode(),9)
    header=struct.pack('<8sIIII',b'TRISTY1\0',len(metadata),len(payload),len(manifest['convs']),1)
    blob=header+metadata+payload;path.write_bytes(blob)
    totals.update({'header_bytes':len(header),'compressed_metadata_bytes':len(metadata),'total_bytes':len(blob),'limit_bytes':500000,'fits_500KB':len(blob)<=500000,'sha256':hashlib.sha256(blob).hexdigest(),'all_three_experts_included':True,'scalars_and_graph_metadata_included':True})
    path.with_suffix('.index.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    path.with_suffix('.bytes.json').write_text(json.dumps(totals,indent=2))
    if len(blob)>500000:raise RuntimeError('Deployment pack exceeds strict 500000-byte limit')
    return totals
def load_pack(path):
    torch.backends.quantized.engine='onednn'
    blob=pathlib.Path(path).read_bytes();magic,nmeta,nbody,nconv,version=struct.unpack('<8sIIII',blob[:24]);assert magic==b'TRISTY1\0' and version==1 and len(blob)==24+nmeta+nbody
    manifest=json.loads(zlib.decompress(blob[24:24+nmeta]));body=memoryview(blob)[24+nmeta:]
    with warnings.catch_warnings():
        warnings.simplefilter('ignore');q=make_prepared(TriStyle())
        with torch.inference_mode():
            for s in range(3):q(torch.zeros(1,3,32,32),s)
        q.eval();q.apply(disable_observer);q=convert(q,inplace=False)
    mods=dict(q.named_modules())
    def arr(d,key,dtype):off,n=d[key];return np.frombuffer(body[off:off+n],dtype=dtype).copy()
    for d in manifest['convs']:
        w=torch.from_numpy(arr(d,'weight','i1').reshape(d['shape']));sc=torch.from_numpy(arr(d,'weight_scale','<f4').astype(np.float64));zp=torch.zeros(sc.numel(),dtype=torch.int64)
        qw=torch._make_per_channel_quantized_tensor(w,sc,zp,0)
        bi=arr(d,'bias','<i4');b=torch.from_numpy((bi*d['input_scale']*sc.numpy()).astype(np.float32))
        mod=mods[d['name']];mod.set_weight_bias(qw,b);mod.scale=d['output_scale'];mod.zero_point=d['output_zp']
    sd=q.state_dict()
    for k,v in manifest['scalar_state'].items():sd[k]=torch.tensor(v,dtype=sd[k].dtype).reshape(sd[k].shape)
    q.load_state_dict(sd);return q.eval()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--checkpoint',required=True);ap.add_argument('--output',default='deployment');ap.add_argument('--calibration',type=int,default=24);a=ap.parse_args()
    torch.set_num_threads(4);torch.backends.quantized.engine='onednn'
    out=ROOT/a.output;out.mkdir(parents=True,exist_ok=True)
    sd=torch.load(a.checkpoint,map_location='cpu',weights_only=False);fp=TriStyle().eval();fp.load_state_dict(sd['model'])
    fake=make_prepared(fp);train=json.loads((ROOT/'data/splits.json').read_text())['train']
    with torch.inference_mode():
        for p in train[:a.calibration]:
            x=image_tensor(ROOT/p,(256,192)).unsqueeze(0)
            for s in range(3):fake(x,s)
    fake.eval();fake.apply(disable_observer);q=convert(copy.deepcopy(fake),inplace=False).eval()
    example=image_tensor(ROOT/train[0],(160,120)).unsqueeze(0)
    with torch.inference_mode():
        for s in range(3):q(example,s)
    totals=pack(q,out/'tristyle_all.bin',example)
    restored=load_pack(out/'tristyle_all.bin')
    # Serialize the packed integer-bias model, so host and FPGA share one contract.
    q=restored
    # Executable CPU integer inference actually invoked before serialization.
    scripted=torch.jit.script(q);scripted.save(str(out/'tristyle_int8.ts'))
    torch.save({'model':fp.state_dict(),'source_checkpoint':str(pathlib.Path(a.checkpoint).resolve()),'source_step':sd['step']},out/'tristyle_fp32.pt')
    torch.save(fake.state_dict(),out/'fake_int8_state.pt')
    from PIL import Image
    from prepare_data import save_gallery
    metrics=[];files=[];labels=[]
    for file in sorted((ROOT/'data/test').glob('*.png')):
        x=image_tensor(file,(320,240)).unsqueeze(0)
        for s in range(3):
            with torch.inference_mode():
                yf=fp(x,s);ys=fake(x,s);t=time.perf_counter();yi=scripted(x,s);elapsed=time.perf_counter()-t;yr=restored(x,s)
            mse=float((yf-yi).square().mean());fm=float((ys-yi).square().mean())
            from skimage.metrics import structural_similarity
            fa=yf[0].permute(1,2,0).numpy();ia=yi[0].permute(1,2,0).numpy()
            row={'input':file.name,'style':STYLES[s],'FP32_to_integer_PSNR_dB':float(-10*np.log10(max(mse,1e-12))),'FP32_to_integer_SSIM':float(structural_similarity(fa,ia,channel_axis=2,data_range=1.)),'fake_to_integer_PSNR_dB':float(-10*np.log10(max(fm,1e-12))),'pack_reload_max_abs_error':float((yr-yi).abs().max()),'CPU_integer_inference_sec_320x240':elapsed,'source_step':sd['step'],'note':'Quantization retention ONLY; not artistic quality or FPGA throughput.'}
            metrics.append(row)
            for name,y in [('fp32',yf),('fake',ys),('integer',yi)]:
                p=out/'comparison'/f'{file.stem}_{STYLES[s]}_{name}.png';p.parent.mkdir(exist_ok=True)
                Image.fromarray((y[0].clamp(0,1).permute(1,2,0).numpy()*255).round().astype(np.uint8)).save(p);files.append(p);labels.append(file.stem+' '+STYLES[s]+' '+name)
    (out/'quantization_metrics.json').write_text(json.dumps({'checkpoint':str(a.checkpoint),'source_step':sd['step'],'calibration_images':a.calibration,'mode':'PTQ with fake INT8 calibration; no QAT claim','metrics':metrics},indent=2))
    save_gallery(files,out/'quantization_contact_sheet.jpg',labels,columns=3)
    print(json.dumps(totals,indent=2),flush=True)
if __name__=='__main__':main()
