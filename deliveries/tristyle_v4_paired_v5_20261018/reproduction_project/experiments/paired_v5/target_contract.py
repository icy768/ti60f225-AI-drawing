"""P1 functional checks; neither aesthetic quality nor student success."""
from pathlib import Path
import argparse,json,sys
import numpy as np
from PIL import Image
import cv2
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(Path(__file__).parent))
from teacher_snapshot import load_teacher

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--targets',default='targets_05');args=ap.parse_args()
    cv2.setNumThreads(2);out=ROOT/'reports/paired_v5/P1'/args.targets;t,assets=load_teacher(out);manifest=json.loads((out/'preview_manifest.json').read_text());r=manifest['rows'][0];a=np.array(Image.open(r['input']).convert('RGB'),copy=True).astype(np.float32)/255;mask=np.array(Image.open(r['mask']).convert('L'),copy=True).astype(np.float32)/255 if r['mask'] else np.zeros(a.shape[:2],np.float32)
    rows=[]
    for style,fn in zip(t.STYLES,(t.vangogh,t.ukiyoe,t.ink)):
        y,s=fn(a,mask,assets);z,_=fn(a,mask,assets);assert y.shape==a.shape and np.isfinite(y).all() and 0<=y.min()<=y.max()<=1;assert np.array_equal(y,z)
        saved=np.array(Image.open(out/'native'/f"{r['name']}_{style}_TEACHER.png"));assert np.array_equal((y*255).round().astype(np.uint8),saved)
        rows.append({'style':style,'finite_shape_range':True,'same_input_two_calls_exact':True,'saved_pixels_match':True,'mean':float(y.mean()),'min':float(y.min()),'max':float(y.max())})
    (out/'functional_contract.json').write_text(json.dumps({'source_sha256':t.sha(t.__file__),'protocol':'one prespecified validation input, 2 executions/style; source and saved target check','limitations':'does not establish locality/equivariance, artistic quality, temporal stability or student learnability','results':rows},indent=2));print(json.dumps(rows),flush=True)
if __name__=='__main__':main()
