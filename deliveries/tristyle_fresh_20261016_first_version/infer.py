import argparse,pathlib
import torch,numpy as np
from PIL import Image
from model import TriStyle,STYLES
from data import image_tensor
def main():
    p=argparse.ArgumentParser();p.add_argument('--weights',required=True);p.add_argument('--input',required=True);p.add_argument('--output',required=True);p.add_argument('--style',choices=list(STYLES)+['all'],default='all');p.add_argument('--device',default='cpu');p.add_argument('--width',type=int,default=640);p.add_argument('--height',type=int,default=480);a=p.parse_args()
    torch.set_num_threads(4);torch.backends.quantized.engine='onednn'
    if a.weights.endswith('.bin'):
        from export_int8 import load_pack
        m=load_pack(a.weights);assert a.device=='cpu'
    elif a.weights.endswith('.ts'):m=torch.jit.load(a.weights,map_location=a.device).eval()
    else:
        m=TriStyle().to(a.device).eval();m.load_state_dict(torch.load(a.weights,map_location='cpu',weights_only=False)['model'])
    x=image_tensor(a.input,(a.width,a.height)).unsqueeze(0).to(a.device);out=pathlib.Path(a.output);out.mkdir(parents=True,exist_ok=True)
    with torch.inference_mode():
        for s in range(3):
            if a.style!='all' and a.style!=STYLES[s]:continue
            y=m(x,s)[0].clamp(0,1).cpu().permute(1,2,0).numpy();Image.fromarray((y*255).round().astype(np.uint8)).save(out/(pathlib.Path(a.input).stem+'_'+STYLES[s]+'.png'))
if __name__=='__main__':main()
