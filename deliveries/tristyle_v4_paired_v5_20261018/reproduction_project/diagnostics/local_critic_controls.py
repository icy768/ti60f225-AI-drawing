"""Training-only critic morphology controls; not an artistic quality score."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import sys

import numpy as np
from PIL import Image,ImageDraw
import torch
from torch import nn
from torch.nn import functional as F

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'experiments'))
from local_adversarial_pilot import PatchCritic,critic_view,ReplicateV4,ContentMask,STYLES,gray,smooth


def pixels(x):
    return Image.fromarray((x.clamp(0,1).permute(1,2,0).numpy()*255).round().astype(np.uint8))


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--checkpoint',type=Path,required=True)
    ap.add_argument('--run',required=True);ap.add_argument('--samples',type=int,default=24)
    args=ap.parse_args();torch.set_num_threads(2)
    random.seed(20261045);torch.manual_seed(20261045);np.random.seed(20261045)
    out=ROOT/'reports'/args.run;out.mkdir(exist_ok=False)
    ck=torch.load(args.checkpoint,map_location='cpu',weights_only=False)
    assert not ck['config'].get('neutral_ink',False),'This control currently uses original ReplicateV4 graph only'
    model=ReplicateV4(.35,.65).eval();model.load_state_dict(ck['model'])
    critics=nn.ModuleList([PatchCritic() for _ in STYLES]).eval();critics.load_state_dict(ck['critics'])
    parent=args.checkpoint.parent
    members=json.loads((parent/'art_bank/real_members.json').read_text())
    refs=json.loads((ROOT/'data/curated_references_v3.json').read_text())['references']
    paths={r['id']:ROOT/r['path'] for r in refs}
    ds=ContentMask(256);indices=random.sample(range(len(ds)),args.samples)
    inputs=torch.stack([ds[i][0] for i in indices])
    examples=[];results={}
    with torch.no_grad():
        for si,style in enumerate(STYLES):
            real=[];chosen=[]
            for _ in range(args.samples):
                tag=random.choice(list(members['members'][style]));m=random.choice(members['members'][style][tag])
                a=np.array(Image.open(paths[m['reference_id']]).convert('RGB').crop(m['box']).resize((128,128),Image.Resampling.LANCZOS),copy=True).astype(np.float32)/255.
                if style=='ink':
                    lo,hi=members['ink_ranges'][m['reference_id']]
                    g=a@np.array([.299,.587,.114],np.float32)
                    g=np.clip(.04+.93*(g-lo)/max(.1,hi-lo),.02,1.)
                    a=np.repeat(g[...,None],3,-1)
                real.append(torch.from_numpy((a*255).round().astype(np.uint8)).permute(2,0,1).float()/255.)
                chosen.append({'tag':tag,**m})
            real=torch.stack(real)
            ys=[]
            for i in range(0,args.samples,3):ys.append(model(inputs[i:i+3],si))
            y=torch.cat(ys)[:,:,64:192,64:192];x=inputs[:,:,64:192,64:192]
            shuffled=real.flatten(2)[:,:,torch.randperm(128*128)].reshape_as(real)
            controls={'real':real,'real_pixel_shuffle':shuffled,'input_photo':x,'student':y,
                      'student_blur9':smooth(y,9),'student_sharpen':(y+.5*(y-smooth(y,5))).clamp(0,1)}
            scores={}
            for label,z in controls.items():
                scores[label]=critics[si](critic_view(z,style)).mean((1,2,3)).numpy()
            summary={k:{'mean':float(v.mean()),'std':float(v.std()),'values':v.tolist()} for k,v in scores.items()}
            summary['real_minus_shuffled_mean']=float((scores['real']-scores['real_pixel_shuffle']).mean())
            summary['blur_minus_student_mean']=float((scores['student_blur9']-scores['student']).mean())
            summary['sharpen_minus_student_mean']=float((scores['student_sharpen']-scores['student']).mean())
            results[style]=summary
            sheet=Image.new('RGB',(128*6,154*4),'white');draw=ImageDraw.Draw(sheet)
            for row in range(4):
                for col,(label,z) in enumerate(controls.items()):
                    sheet.paste(pixels(z[row]),(col*128,row*154))
                    draw.text((col*128+2,row*154+129),label,fill='black')
                    draw.text((col*128+2,row*154+141),f'D {scores[label][row]:.3f}',fill='black')
            sheet.save(out/f'{style}_CRITIC_CONTROLS_NOT_QUALITY.jpg',quality=95)
            examples.append({'style':style,'real_members':chosen})
            print(style,json.dumps({k:v for k,v in summary.items() if not isinstance(v,dict)}))
    report={'kind':'Measured CPU controls of a learned TRAINING critic; NOT student art/generalization/FPGA evidence',
            'checkpoint':str(args.checkpoint.resolve()),'checkpoint_sha256':hashlib.sha256(args.checkpoint.read_bytes()).hexdigest(),
            'samples_per_style':args.samples,'training_image_files':[str(ds.files[i]) for i in indices],
            'scope':'Fixed17/heldout video not evaluated or optimized. Same source training domains as critic training.',
            'limitation':'Pixel shuffling changes gradients/spectrum as well as continuity; score differences are shortcut diagnostics, not a pure long-stroke causal test.',
            'results':results,'reference_members':examples,'promoted':False}
    (out/'controls.json').write_text(json.dumps(report,indent=2),encoding='utf-8')


if __name__=='__main__':main()
