"""Check new checkpoint train/eval forward vs separately exported golden."""
from pathlib import Path
import sys,json
import numpy as np,torch
from PIL import Image
R=Path(__file__).resolve().parent;sys.path.insert(0,str(R/'algo'))
from r44_forward import TinyStyleNet,QCfg
import golden
torch.set_num_threads(4);QCfg.enabled=True;QCfg.observe=False
f=json.loads((R/'F0/RESULT.json').read_text(encoding='utf-8'));p=Path(f['inputs'][1]['path']);im=np.array(Image.open(p).convert('RGB'));x=torch.from_numpy(im).permute(2,0,1)[None].float()/255
rows=[]
for ident in ['D1B60','D2B','D3B','J1_60','D0']:
 run=R/f'runs/r44_{ident.lower()}/student.pt';export=R/f'R44/{ident}_qparams.npz'
 if not run.exists() or not export.exists():continue
 ck=torch.load(run,map_location='cpu',weights_only=False);net=TinyStyleNet(**ck['cfg']).eval();net.load_state_dict(ck['sd']);q=golden.load(str(export.with_suffix('')))
 for si,sty in enumerate(q['styles']):
  with torch.no_grad():y=net(x,torch.tensor([si]))
  a=(y[0].permute(1,2,0).numpy()*255).round().astype(np.uint8);b,_,_=golden.run(q,im,si)
  delta=abs(a.astype(float)-b.astype(float));row={'id':ident,'style':sty,'native640':True,'mae_255':float(delta.mean()),'max_lsb':int(delta.max()),'mismatch':int(np.count_nonzero(delta))};assert row['mismatch']==0,row;rows.append(row)
(R/'R44/CANDIDATE_FIDELITY.json').write_text(json.dumps({'pass':True,'input_path':str(p),'rows':rows,'limits':'one native640 heldout input x3 styles per completed candidate; CPU only, not CPU-RTL'},indent=2),encoding='utf-8');print('new checkpoint integer fidelity0LSB',len(rows),'cases')
