"""Create the final v21b same-input Skill/FP32/INT8 comparison."""
from pathlib import Path
import json
import numpy as np
from PIL import Image, ImageDraw, ImageOps
import torch
import golden
from tinystyle import QCfg, TinyStyleNet
from train import ROOT

def rgb(y): return (y[0].permute(1,2,0).detach().cpu().numpy()*255).round().clip(0,255).astype(np.uint8)

def main():
    root=Path(ROOT); out=root/'audits/v21_selected_city_comparison'; out.mkdir(parents=True,exist_ok=False)
    inp=root/'audits/v15_v6_restart_20261005/new_scenes_comparisons/city_street_000000026204_input.png'
    skill_dir=root/'audits/skill_network_comparison'
    ck=torch.load(root/'runs/art_styles_c24_v21b_ukiyoe_color_block/student.pt',map_location='cpu',weights_only=False)
    qat=torch.load(root/'runs/art_styles_c24_v21b_ukiyoe_qat900_soft15/student.pt',map_location='cpu',weights_only=False)
    QCfg.enabled=QCfg.observe=False; net=TinyStyleNet(**ck['cfg']).cuda().eval(); net.load_state_dict(ck['sd']); q=golden.load(str(root/'audits/v21b_ukiyoe_qat900_soft15_export'))
    source=np.asarray(Image.open(inp).convert('RGB')); x=torch.from_numpy(source.copy()).permute(2,0,1)[None].cuda().float()/255
    skills={'van_gogh':skill_dir/'city_street_skill_vangogh_imagegen.png','ukiyo_e':skill_dir/'city_street_skill_ukiyoe_imagegen.png','ink_landscape':skill_dir/'city_street_skill_ink_imagegen.png'}
    W,H=360,270; sheet=Image.new('RGB',(4*W,3*(H+34)),'white'); draw=ImageDraw.Draw(sheet); labels=['Input','Skill teacher','v21b FP32','v21b INT8']; rows=[]
    for ri,style in enumerate(ck['styles']):
        si=ck['styles'].index(style)
        with torch.no_grad(): fp=rgb(net(x,torch.tensor([si],device='cuda')))
        hard,_,_=golden.run(q,source,si); sk=np.asarray(Image.open(skills[style]).convert('RGB'))
        for ci,arr in enumerate((source,sk,fp,hard)):
            im=ImageOps.contain(Image.fromarray(arr),(W,H),Image.Resampling.LANCZOS); x0=ci*W+(W-im.width)//2; y0=ri*(H+34)+34+(H-im.height)//2; sheet.paste(im,(x0,y0)); draw.text((ci*W+6,ri*(H+34)+8),labels[ci],fill='black')
        draw.text((4*W-110,ri*(H+34)+8),style,fill='black')
        Image.fromarray(fp).save(out/f'city_street_{style}_v21b_fp32.png'); Image.fromarray(hard).save(out/f'city_street_{style}_v21b_int8.png')
        rows.append({'style':style,'skill':str(skills[style].resolve()),'fp32':str((out/f'city_street_{style}_v21b_fp32.png').resolve()),'int8':str((out/f'city_street_{style}_v21b_int8.png').resolve())})
    path=out/'city_street_skill_vs_v21b.jpg'; sheet.save(path,quality=96); (out/'manifest.json').write_text(json.dumps({'input':str(inp.resolve()),'model_float':'runs/art_styles_c24_v21b_ukiyoe_color_block/student.pt','model_int8':'runs/art_styles_c24_v21b_ukiyoe_qat900_soft15/student.pt','qparams':'audits/v21b_ukiyoe_qat900_soft15_export','rows':rows,'note':'v21b is the balanced candidate; its supervision targets Ukiyo-e while retaining the shared three-style model.'},ensure_ascii=False,indent=2),encoding='utf-8'); print(path.resolve())
if __name__=='__main__': main()
