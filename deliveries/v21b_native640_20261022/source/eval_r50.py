"""Integer blind comparison on exact F0 held-out inputs, never training them."""
from pathlib import Path
import argparse,sys,json,hashlib,random
import numpy as np
import torch
from PIL import Image,ImageDraw
R=Path(__file__).resolve().parent;sys.path.insert(0,str(R/'algo'));import golden
torch.set_num_threads(4)
p=argparse.ArgumentParser();p.add_argument('--id',required=True);p.add_argument('--run',required=True);p.add_argument('--style',type=int,required=True);a=p.parse_args()
O=R/'R44'/a.id;O.mkdir(exist_ok=True)
q0=golden.load(str(R/'R44/D1B60_qparams'));q1=golden.load(str(R/f'R44/{a.id}_qparams'))
f=json.loads((R/'F0/RESULT.json').read_text(encoding='utf-8'))
rng=random.Random(44044);key={};rows=[];html=['<!doctype html><meta charset="utf-8"><title>R44 integer blind</title><h1>J6 vs D1B60 CPU integer blind: unadopted, no board test</h1><p>Same input, native640 generated; views may be scaled to fit. A/B identities in key.json, not in page.</p>']
for j,inp in enumerate(f['inputs']):
 im=np.array(Image.open(inp['path']).convert('RGB'));assert im.shape==(480,640,3)
 for si,sty in enumerate(q0['styles']):
  y0,_,_=golden.run(q0,im,si);y1,_,dumps=golden.run(q1,im,si,dump=True)
  if a.style>=0 and si!=a.style:assert np.array_equal(y0,y1),'non-target style changed'
  order=[('D1B60',y0),('candidate',y1)];rng.shuffle(order);key[f'{j}_{sty}']={k:v[0] for k,v in zip(['A','B'],order)}
  sheet=Image.new('RGB',(1920,510),'white');d=ImageDraw.Draw(sheet)
  for col,(label,img) in enumerate([('Input',im),('A',order[0][1]),('B',order[1][1])]):sheet.paste(Image.fromarray(img),(col*640,30));d.text((col*640+8,8),label,fill='black')
  name=f'{j}_{sty}.jpg';sheet.save(O/name,quality=95);Image.fromarray(y1).save(O/f'{j}_{sty}_candidate.png')
  html.append(f'<h2>Input{j} {sty}</h2><a href="{name}"><img src="{name}" width="1440"></a>')
  rows.append({'input':j,'style':sty,'candidate_vs_D1B60_mae':float(np.mean(np.abs(y1.astype(float)-y0.astype(float)))),'non_target_exact':bool(np.array_equal(y0,y1)) if si!=a.style and a.style>=0 else None,'coefficient_boundaries':[{'layer':i,'M_boundary':int(np.count_nonzero((z['M']==-131072)|(z['M']==131071))),'B_boundary':int(np.count_nonzero((z['B']==-524288)|(z['B']==524287))),'A_boundary':int(np.count_nonzero((z['a']==-262144)|(z['a']==262143)))} for i,z in enumerate(dumps)]})
ck=torch.load(R/a.run/'student.pt',map_location='cpu',weights_only=False);base=torch.load(R/'runs/r44_j1_60/student.pt',map_location='cpu',weights_only=False)
changed=[k for k,v in ck['sd'].items() if not torch.equal(v,base['sd'][k])]
assert not any(k.endswith('aq.rmax') for k in changed)
if a.style>=0:assert all('norm.gamma' in k or 'norm.beta' in k for k in changed)
(O/'index.html').write_text('\n'.join(html),encoding='utf-8');(O/'key.json').write_text(json.dumps(key,indent=2),encoding='utf-8')
(O/'RESULT.json').write_text(json.dumps({'rows':rows,'changed_sd_fields_vs_training_parent_J1_60':changed,'visual_comparator':'D1B60','art_gate':'AWAIT_SUPERVISION','adopted':False,'board_validated':False,'research_only':True},indent=2),encoding='utf-8');print('INTEGER BLIND READY',a.id)
