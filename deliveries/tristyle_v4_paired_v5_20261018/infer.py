"""Portable inference; runtime/ and models/ live beside this file in the bundle."""
from pathlib import Path
import argparse
import hashlib
import json
import sys
import numpy as np
from PIL import Image
import torch
from torch.nn import functional as F

HOME=Path(__file__).resolve().parent
sys.path.insert(0,str(HOME/'runtime'))
STYLES=('vangogh','ukiyoe','ink')


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--input',required=True);ap.add_argument('--output',required=True)
    ap.add_argument('--backend',choices=['fp32','fake','onednn','integer'],default='integer')
    ap.add_argument('--style',choices=['all',*STYLES],default='all')
    ap.add_argument('--mode',choices=['native','reduced320'],default='reduced320')
    ap.add_argument('--device',choices=['cpu','cuda'],default='cpu')
    a=ap.parse_args();torch.set_num_threads(3);torch.backends.quantized.engine='onednn'
    output=Path(a.output).resolve();output.mkdir(exist_ok=False,parents=True)
    path=Path(a.input).resolve();raw=np.array(Image.open(path).convert('RGB'),copy=True)
    u=torch.from_numpy(raw).permute(2,0,1)[None]
    if a.mode=='reduced320':
        u=F.interpolate(u.float(),(240,320),mode='bilinear',align_corners=False,antialias=True).round().clamp(0,255).to(torch.uint8)
        h,w=240,320
    else:
        h,w=u.shape[-2:];u=F.pad(u,(0,-w%8,0,-h%8),mode='replicate')
    models=HOME/'models'
    if a.backend=='integer':
        assert a.device=='cpu','Normative integer interpreter runs on CPU'
        from int_ref import IntGraph
        net=IntGraph(models/'all_styles_hw.bin')
        weight=models/'all_styles_hw.bin'
    elif a.backend=='onednn':
        assert a.device=='cpu','oneDNN backend runs on CPU'
        weight=models/'int8.ts';net=torch.jit.load(str(weight)).eval()
    else:
        from model import model_for_state
        ck=torch.load(models/'fp32.pt',map_location='cpu',weights_only=False)['model']
        net=model_for_state(ck)
        if a.backend=='fp32':
            net.load_state_dict(ck);weight=models/'fp32.pt'
        else:
            import quantize as qm
            from consistent_qat import align_weight_fake_quant,simulate_int32_bias
            net=qm.prepared(net);align_weight_fake_quant(net)
            weight=models/'fake_int8_state.pt';net.load_state_dict(torch.load(weight,weights_only=True))
            net.apply(torch.ao.quantization.disable_observer)
            simulate_int32_bias(net,json.loads((models/'input_scales.json').read_text()))
        net=net.to(a.device).eval()
    chosen=range(3) if a.style=='all' else [STYLES.index(a.style)]
    with torch.no_grad():
        for style in chosen:
            if a.backend=='integer':y=net(u,style).float()/255
            else:y=net(u.float().to(a.device)/255,style).detach().cpu().clamp(0,1)
            y=y[:,:,:h,:w]
            im=(y[0].permute(1,2,0).numpy()*255).round().clip(0,255).astype('uint8')
            Image.fromarray(im).save(output/(STYLES[style]+'.png'))
            if a.mode=='reduced320':
                display=F.interpolate(y,(480,640),mode='bilinear',align_corners=False)
                Image.fromarray((display[0].permute(1,2,0).numpy()*255).round().clip(0,255).astype('uint8')).save(output/(STYLES[style]+'_display640x480_REDUCED.png'))
    (output/'RUN.json').write_text(json.dumps({'backend':a.backend,'mode':a.mode,'device':a.device,
        'input_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'weight_sha256':hashlib.sha256(weight.read_bytes()).hexdigest(),
        'torch':torch.__version__,'note':'320x240 internal is reduced-resolution mode. Host execution does not establish FPGA FPS.'},indent=2),encoding='utf8')
    print(str(output))


if __name__=='__main__':main()
