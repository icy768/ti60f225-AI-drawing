"""Guarded P2 paired target generation, at most4 CPU workers. No training.

Do not run until the reviewed G1_APPROVAL.json selects the exact teacher
directory and source hash for each style. Source/targets are immutable per run.
"""
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import argparse, hashlib, json, os, shutil, sys
import numpy as np
from PIL import Image
import cv2

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(Path(__file__).parent))
from teacher_snapshot import load_teacher
STYLES=('vangogh','ukiyoe','ink');CACHE={}
V3=Path(json.loads((ROOT/'baseline/manifest.json').read_text())['V3_root'])
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def generate(job):
    split,p,mp,out,mapping=job;p=Path(p);mp=Path(mp);out=Path(out)
    assert not (out/'STOP').exists(),'P2 STOP requested; existing completed records retained'
    cv2.setNumThreads(1)
    rgb=np.array(Image.open(p).convert('RGB'),copy=True).astype('float32')/255
    mask=np.array(Image.open(mp).convert('L'),copy=True).astype('float32')/255 if mp.is_file() else np.zeros(rgb.shape[:2],np.float32)
    assert mask.shape==rgb.shape[:2]
    valid=np.flatnonzero(rgb.mean((1,2))>.008);top,bottom=(int(valid[0]),int(valid[-1])+1) if len(valid) else (0,rgb.shape[0])
    rows=[]
    for style in STYLES:
        folder=ROOT/mapping[style]['folder']
        key=str(folder)
        if key not in CACHE:CACHE[key]=load_teacher(folder)
        teacher,assets=CACHE[key];assert teacher.sha(teacher.__file__)==mapping[style]['source_sha256']
        target,stats=getattr(teacher,style)(rgb[top:bottom],mask[top:bottom],assets)
        assert target.shape==rgb[top:bottom].shape and np.isfinite(target).all() and target.min()>=0 and target.max()<=1
        full=rgb.copy();full[top:bottom]=target;dest=out/style/split/p.name
        dest.parent.mkdir(parents=True,exist_ok=True);tmp=dest.with_suffix('.tmp.png')
        Image.fromarray((full*255).round().astype('uint8')).save(tmp);tmp.replace(dest)
        rows.append({'style':style,'path':str(dest.relative_to(ROOT)),'sha256':sha(dest),'stats':stats,'active_rows':[top,bottom]})
    record={'input':str(p),'input_sha256':sha(p),'mask':str(mp) if mp.exists() else None,'mask_sha256':sha(mp) if mp.exists() else None,'split':split,'targets':rows}
    rp=out/'records'/split/(p.stem+'.json');rp.parent.mkdir(parents=True,exist_ok=True);tmp=rp.with_suffix('.tmp');tmp.write_text(json.dumps(record,indent=2));tmp.replace(rp)
    return record

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);ap.add_argument('--workers',type=int,default=4);ap.add_argument('--resume',action='store_true');a=ap.parse_args()
    assert 1<=a.workers<=4
    assert json.loads(Path('D:/ClaudeTest/guidance/OWNER.json').read_text(encoding='utf-8'))['owner']=='codex'
    gate_path=ROOT/'reports/paired_v5/P1/G1_APPROVAL.json'
    assert gate_path.is_file(),'No G1 approval; P2 cannot start'
    gate=json.loads(gate_path.read_text());assert gate['visual_passed'] is True
    mapping=gate['teachers'];assert set(mapping)==set(STYLES)
    for style,meta in mapping.items():
        folder=ROOT/meta['folder'];assert sha(folder/'source_targets_v5.py')==meta['source_sha256'];assert sha(folder/'teacher_assets.json')==meta['assets_sha256']
    out=ROOT/a.out;assert out.resolve().is_relative_to((ROOT/'data/paired_v5').resolve())
    config={'output':a.out,'teachers':mapping,'gate_path':str(gate_path.relative_to(ROOT)),'gate_sha256':sha(gate_path),'source_sha256':sha(__file__),'worker_limit':a.workers,'fixed17_used':False,'heldout_video_used':False}
    out.mkdir(parents=True,exist_ok=True)
    if a.resume:
        original=json.loads((out/'config.json').read_text());assert original==config,'Do not change a dataset generation run'
    else:
        assert not (out/'config.json').exists(),'New dataset run name required'
        (out/'config.json').write_text(json.dumps(config,indent=2));(out/'source_generate_dataset.py').write_bytes(Path(__file__).read_bytes())
        shutil.copyfile(gate_path,out/'G1_APPROVAL.json')
        for style,meta in mapping.items():
            dest=out/'teacher_sources'/style;dest.mkdir(parents=True,exist_ok=True)
            for name in ('source_targets_v5.py','teacher_assets.json','params.json'):shutil.copyfile(ROOT/meta['folder']/name,dest/name)
    splits=json.loads((V3/'data/splits.json').read_text());jobs=[];records=[];counts={}
    for split,expected in [('train',1171),('validation',92)]:
        allowed={Path(p.replace('\\','/')).stem for p in splits[split]}
        files=[p for p in sorted((V3/'data/claude_targets/content'/split).glob('*.png')) if p.stem in allowed]
        assert len(files)==expected,(split,len(files));counts[split]=len(files)
        for p in files:
            mp=V3/'data/claude_targets/content_masks'/split/p.name;rp=out/'records'/split/(p.stem+'.json')
            if a.resume and rp.exists():
                record=json.loads(rp.read_text());assert record['input_sha256']==sha(p)
                assert record['mask_sha256']==(sha(mp) if mp.exists() else None)
                assert len(record['targets'])==3 and all(sha(ROOT[t['path']])==t['sha256'] for t in record['targets']);records.append(record)
            else:jobs.append((split,str(p),str(mp),str(out),mapping))
    print(json.dumps({'counts':counts,'pending':len(jobs),'resumed':len(records),'workers':a.workers}),flush=True)
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        for record in pool.map(generate,jobs,chunksize=1):
            records.append(record)
            if len(records)%25==0:print('P2',len(records),'/1263',flush=True)
    assert len(records)==1263 and sum(len(r['targets']) for r in records)==3789
    manifest={'config':config,'counts':counts,'records':sorted(records,key=lambda r:(r['split'],r['input'])),'all_targets_are_teachers_not_students':True}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2));(out/'finished.json').write_text(json.dumps({'count':1263,'target_images':3789,'manifest_sha256':sha(out/'manifest.json'),'pid':os.getpid()}));print('P2_COMPLETE',flush=True)

if __name__=='__main__':main()
