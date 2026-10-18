"""Measure full-scene vs crop-conditioned teacher ambiguity, not student quality."""
from pathlib import Path
import argparse,json,sys
import cv2,numpy as np
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(Path(__file__).parent))
from teacher_snapshot import load_teacher

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--targets',default='targets_04');args=ap.parse_args()
    cv2.setNumThreads(2);source=ROOT/'reports/paired_v5/P1'/args.targets;t,assets=load_teacher(source);manifest=json.loads((source/'preview_manifest.json').read_text());out=ROOT/'reports/paired_v5/P1'/('locality_'+args.targets.split('_')[-1]);out.mkdir(parents=True,exist_ok=True);result=[]
    # Prespecified first, third and fourth validation rows; no fixed17.
    for idx in (0,2,3):
        r=manifest['rows'][idx];a=np.array(Image.open(r['input']).convert('RGB'),copy=True).astype(np.float32)/255;mask=np.array(Image.open(r['mask']).convert('L'),copy=True).astype(np.float32)/255 if r['mask'] else np.zeros(a.shape[:2],np.float32)
        h,w=a.shape[:2];top,left=(h-256)//2,(w-256)//2;crop=a[top:top+256,left:left+256];mc=mask[top:top+256,left:left+256];sheet=Image.new('RGB',(4*256,3*280),'white');d=ImageDraw.Draw(sheet)
        for si,(style,fn) in enumerate(zip(t.STYLES,(t.vangogh,t.ukiyoe,t.ink))):
            teacher=np.array(Image.open(source/'native'/f"{r['name']}_{style}_TEACHER.png")).astype(np.float32)/255;full=teacher[top:top+256,left:left+256];local,_=fn(crop,mc,assets);diff=np.abs(full-local)
            metrics={'scene':r['name'],'style':style,'crop_box':[left,top,left+256,top+256],'whole256_MAE':float(diff.mean()),'central192_MAE_exclude32px':float(diff[32:-32,32:-32].mean()),'input_context_only_changed':True,'not_student':True};result.append(metrics)
            for col,(label,v) in enumerate(zip(('INPUT CROP','FULL TEACHER CROP','CROP-ONLY TEACHER','ABS DIFFERENCE x4'),(crop,full,local,diff*4))):
                sheet.paste(Image.fromarray((np.clip(v,0,1)*255).round().astype(np.uint8)),(col*256,si*280));d.text((col*256+2,si*280+260),style+' '+label,fill='black')
        sheet.save(out/f"{r['name']}.jpg",quality=95)
    payload={'source_sha256':t.sha(t.__file__),'diagnostic_sha256':t.sha(__file__),'purpose':'Compare teacher label for the identical central input crop under full-image vs crop-only context; this is not an artistic or student gate','limitations':['Full teacher saved uint8, crop teacher float; quantization contributes <=1/510 RGB MAE','Does not isolate each global operation or prove model incapacity','Global CDF/region merging and finite-border filters can all contribute; central192 excludes32px but long paths may still cross it'],'rows':result}
    (out/'result.json').write_text(json.dumps(payload,indent=2));print(json.dumps(result,indent=2),flush=True)
if __name__=='__main__':main()
