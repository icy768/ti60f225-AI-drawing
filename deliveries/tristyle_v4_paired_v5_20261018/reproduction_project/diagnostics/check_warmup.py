"""Foundation reconstruction checks, not style-quality evaluation or promotion."""
import json,pathlib,sys,torch,numpy as np
from PIL import Image,ImageDraw
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'experiments'))
from model_v4_draft import V4Draft
torch.set_num_threads(2)
for run in sorted((ROOT/'experiments').glob('warmup_*')):
 if not(run/'skeleton.pt').exists():continue
 d=torch.load(run/'skeleton.pt',map_location='cpu',weights_only=False);cfg=d['config'];m=V4Draft(cfg['context_width'],cfg['depth'],cfg['head_channels']).eval();m.load_state_dict(d['model']);out=ROOT/'reports/warmup'/run.name;out.mkdir(parents=True,exist_ok=True)
 source=ROOT/'experiments/model_v4_draft.py';assert __import__('hashlib').sha256(source.read_bytes()).hexdigest()==cfg['source_sha256'];(run/'model_source.py').write_bytes(source.read_bytes())
 v3=pathlib.Path(json.loads((ROOT/'baseline/manifest.json').read_text())['V3_root']);p=v3/'data/test/water_day.png';im=Image.open(p).convert('RGB');a=np.array(im,copy=True);h,w=a.shape[:2];padded=np.pad(a,((0,-h%16),(0,-w%16),(0,0)),mode='edge');x=torch.from_numpy(padded).permute(2,0,1)[None].float()/255
 sheet=Image.new('RGB',(640*4,480),'white');q=im.copy();q.thumbnail((640,480));sheet.paste(q,(0,0));rows=[]
 with torch.no_grad():
  for s in range(3):
   y=m(x,s)[0,:,:h,:w];raw=(y.clamp(0,1).permute(1,2,0)*255).round().byte().numpy();Image.fromarray(raw).save(out/f'water_day_style{s}_IDENTITY.png');q=Image.fromarray(raw);q.thumbnail((640,480));sheet.paste(q,((s+1)*640,0));rows.append({'style':s,'MAE':float((y-x[0,:,:h,:w]).abs().mean()),'raw_min':float(y.min()),'raw_max':float(y.max()),'raw_channel_means':y.mean((1,2)).tolist()})
 sheet.save(out/'water_day_IDENTITY_ONLY.jpg',quality=92);(out/'result.json').write_text(json.dumps({'stage':'identity only;not style quality', 'rows':rows},indent=1));print(run.name,rows,flush=True)
