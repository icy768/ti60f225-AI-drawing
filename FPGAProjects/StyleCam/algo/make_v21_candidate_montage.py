"""Visualize the selected v21 float candidates on the same city photo."""
from pathlib import Path
import json
import numpy as np
from PIL import Image, ImageDraw, ImageOps
import torch
from tinystyle import QCfg, TinyStyleNet
from train import ROOT

def rgb(y):
    return (y[0].permute(1,2,0).detach().cpu().numpy()*255).round().clip(0,255).astype(np.uint8)

def main():
    root=Path(ROOT); out=root/'audits/v21_candidate_comparison'; out.mkdir(parents=True,exist_ok=False)
    inp=root/'audits/v15_v6_restart_20261005/new_scenes_comparisons/city_street_000000026204_input.png'
    skill_dir=root/'audits/skill_network_comparison'
    base_ck=torch.load(root/'runs/art_styles_c24_v19_expanded_skill/student.pt',map_location='cpu',weights_only=False)
    models={
      'base': 'runs/art_styles_c24_v19_expanded_skill/student.pt',
      'van_gogh': 'runs/art_styles_c24_v21c_vg_texture/student.pt',
      'ukiyo_e': 'runs/art_styles_c24_v21b_ukiyoe_color_block/student.pt',
      'ink_landscape': 'runs/art_styles_c24_v19_expanded_skill/student.pt',
    }
    nets={}
    QCfg.enabled=QCfg.observe=False
    for key,path in models.items():
        ck=torch.load(root/path,map_location='cpu',weights_only=False)
        net=TinyStyleNet(**ck['cfg']).cuda().eval(); net.load_state_dict(ck['sd']); nets[key]=net
    source=np.asarray(Image.open(inp).convert('RGB')); x=torch.from_numpy(source.copy()).permute(2,0,1)[None].cuda().float()/255
    skill={'van_gogh':skill_dir/'city_street_skill_vangogh_imagegen.png','ukiyo_e':skill_dir/'city_street_skill_ukiyoe_imagegen.png','ink_landscape':skill_dir/'city_street_skill_ink_imagegen.png'}
    W,H=360,270; sheet=Image.new('RGB',(4*W,3*(H+34)),'white'); draw=ImageDraw.Draw(sheet)
    labels=['Input','v19 base','Skill teacher','v21 candidate']
    rows=[]
    for ri,style in enumerate(base_ck['styles']):
        si=base_ck['styles'].index(style); candidate=nets[style]
        with torch.no_grad(): base=rgb(nets['base'](x,torch.tensor([si],device='cuda'))); cand=rgb(candidate(x,torch.tensor([si],device='cuda')))
        sk=np.asarray(Image.open(skill[style]).convert('RGB'))
        for name,arr in [('input',source),('base',base),('skill',sk),('candidate',cand)]: Image.fromarray(arr).save(out/f'city_street_{style}_{name}.png')
        panel=[source,base,sk,cand]
        for ci,arr in enumerate(panel):
            im=ImageOps.contain(Image.fromarray(arr),(W,H),Image.Resampling.LANCZOS); x0=ci*W+(W-im.width)//2; y0=ri*(H+34)+34+(H-im.height)//2; sheet.paste(im,(x0,y0)); draw.text((ci*W+6,ri*(H+34)+8),labels[ci],fill='black')
        draw.text((4*W-110,ri*(H+34)+8),style,fill='black')
        rows.append({'style':style,'candidate':models[style],'skill':str(skill[style].resolve())})
    path=out/'city_street_v21_candidates.jpg'; sheet.save(path,quality=96)
    (out/'manifest.json').write_text(json.dumps({'input':str(inp.resolve()),'rows':rows,'note':'v21 float candidates only; no integer output until a candidate passes the 8-image gate.'},ensure_ascii=False,indent=2),encoding='utf-8')
    print(path.resolve())
if __name__=='__main__': main()
