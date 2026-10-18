"""Audit the actual short/long routing of offline VG teachers, not art quality."""
from pathlib import Path
import json,sys
import cv2,numpy as np
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(Path(__file__).parent))
from teacher_snapshot import load_teacher

def main():
    cv2.setNumThreads(2);folder=ROOT/'reports/paired_v5/P1/targets_08';t,assets=load_teacher(folder);manifest=json.loads((folder/'preview_manifest.json').read_text());out=ROOT/'reports/paired_v5/P1/stroke_scale_08';assert not out.exists();out.mkdir(parents=True);rows=[]
    for idx,r in enumerate(manifest['rows']):
        a=np.array(Image.open(r['input']).convert('RGB'),copy=True).astype(np.float32)/255;g=t.gray(a);_,_,energy=t.field(a);detail=np.clip(energy/.045,0,1);hp=g-t.blur(g,1.2);texture=np.sqrt(t.blur(hp*hp,4));textured=texture>.02
        row={'scene':r['name'],'energy_quantiles':np.quantile(energy,[.1,.5,.9,.99]).tolist(),'detail_quantiles':np.quantile(detail,[.1,.5,.9,.99]).tolist(),'textured_fraction_HP_RMS_gt_002':float(textured.mean()),'mean_short_route_in_textured':float(detail[textured].mean()) if textured.any() else None,'textured_pixels_given_majority_long_route':float((detail[textured]<.5).mean()) if textured.any() else None};rows.append(row)
        if idx in (1,2,8):
            sheet=Image.new('RGB',(4*256,280),'white');d=ImageDraw.Draw(sheet)
            for col,(label,v) in enumerate(zip(('INPUT','CURRENT SHORT WEIGHT','HP RMS x10','TEXTURED but LONG'),(a,np.repeat(detail[...,None],3,-1),np.repeat((texture*10)[...,None],3,-1),np.repeat((textured&(detail<.5))[...,None],3,-1).astype(np.float32)))):
                im=Image.fromarray((np.clip(v,0,1)*255).round().astype(np.uint8));im.thumbnail((256,250));sheet.paste(im,(col*256,0));d.text((col*256+2,258),label,fill='black')
            sheet.save(out/f"{r['name']}.jpg",quality=95)
    result={'teacher_source_sha256':t.sha(t.__file__),'diagnostic_sha256':t.sha(__file__),'rows':rows,'limitations':'HP RMS is a texture proxy, not semantics. This checks scale-routing implementation only, never artistic pass.'}
    (out/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(rows,indent=2),flush=True)
if __name__=='__main__':main()
