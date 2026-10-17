"""Reproducible delivery pipeline, stage failures recorded; no automatic artistic acceptance."""
import argparse, datetime, hashlib, json, pathlib, subprocess, sys, time, shutil, platform
ROOT=pathlib.Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser(); ap.add_argument('--checkpoint',required=True); ap.add_argument('--out',required=True)
ap.add_argument('--qat-steps',type=int,default=120); ap.add_argument('--qat-device',default='cpu')
ap.add_argument('--robust-calibration',action='store_true'); ap.add_argument('--native-video-frames',type=int,default=150)
ap.add_argument('--skip-export',action='store_true'); ap.add_argument('--fullres-video',action='store_true'); a=ap.parse_args()
dep=ROOT/a.out; dep.mkdir(parents=True,exist_ok=True); rows=[]; started=time.time()
snapshot=dep/('validation_source_snapshot' if a.skip_export else 'export_source_snapshot');snapshot.mkdir(exist_ok=True)
for folder in ('claude_impl','continuation_impl'):
    dest=snapshot/folder;dest.mkdir(exist_ok=True)
    for p in (ROOT/folder).glob('*.py'):shutil.copy2(p,dest/p.name)
source_hashes={str(p.relative_to(snapshot)):hashlib.sha256(p.read_bytes()).hexdigest() for p in snapshot.rglob('*.py')}
(snapshot/'SOURCE_HASHES.json').write_text(json.dumps(source_hashes,indent=1))
(dep/'pipeline_environment.json').write_text(json.dumps({'python':sys.version,'platform':platform.platform(),'executable':sys.executable,
    'args':vars(a),'start':datetime.datetime.now().astimezone().isoformat(),
    'data_manifest_sha256':hashlib.sha256((ROOT/'data/USED_DATA_manifest.json').read_bytes()).hexdigest()},indent=2))
def run(name,args):
    t=time.time(); cmd=[sys.executable,'-u',*args]; print('STAGE',name,flush=True)
    with (dep/(name+'.log')).open('w',encoding='utf-8') as f:
        process=subprocess.Popen(cmd,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
        (dep/'pipeline_status.json').write_text(json.dumps({'args':vars(a),'stages':rows,'active_stage':name,'active_pid':process.pid,
            'active_command':cmd,'started_at':datetime.datetime.now().astimezone().isoformat(),'art_accepted':False},indent=2))
        code=process.wait()
    row={'name':name,'command':cmd,'returncode':code,'seconds':time.time()-t,
         'completed_at':datetime.datetime.now().astimezone().isoformat()}; rows.append(row)
    (dep/'pipeline_status.json').write_text(json.dumps({'args':vars(a),'stages':rows,'elapsed':time.time()-started,'art_accepted':False},indent=2))
    if code: raise SystemExit(f'Stage failed: {name}, see log')
if not a.skip_export:
    args=['claude_impl/quantize.py','--checkpoint',a.checkpoint,'--out',a.out,'--qat-steps',str(a.qat_steps),'--qat-objective','preserve','--qat-batch','1','--device',a.qat_device,'--targets','vangogh_p1,ukiyoe_p1,ink_p1']
    if a.robust_calibration: args.append('--robust-calibration')
    run('01_export',args)
run('02_fixed_pack',['claude_impl/hwpack.py',str(dep/'tristyle_v3_all.bin'),str(dep/'tristyle_v3_hw.bin')])
run('03_format_equality',['supervisor/verify_hwpack.py',a.out])
run('04_numeric_all17',['continuation_impl/validate_delivery.py',a.out,'--native-gallery'])
run('05_hardware',['continuation_impl/hardware_final.py','--pack',str(dep/'tristyle_v3_hw.bin'),'--out',str(dep/'hardware')])
for tag,arg in (('fp32','--checkpoint'),('int8','--ts'),('integer_reference','--pack')):
    frames=a.native_video_frames if arg=='--pack' else 150
    path=dep/('tristyle_v3_fp32.pt' if arg=='--checkpoint' else 'tristyle_v3_int8.ts' if arg=='--ts' else 'tristyle_v3_hw.bin')
    run('06_video_'+tag,['claude_impl/video_eval.py',arg,str(path),'--out',str(dep/'video'),'--start','640','--frames',str(frames),'--size','320x240','--device','cpu'])
    run('07_codec_'+tag,['continuation_impl/video_codec.py',str(dep/'video'/('heldout_'+tag+'.mp4'))])
if a.fullres_video:
    for tag,arg in (('fp32','--checkpoint'),('int8','--ts'),('integer_reference','--pack')):
        path=dep/('tristyle_v3_fp32.pt' if arg=='--checkpoint' else 'tristyle_v3_int8.ts' if arg=='--ts' else 'tristyle_v3_hw.bin')
        start,frames=760,30  # same native-size person segment for all three backends
        run('08_full640_'+tag,['claude_impl/video_eval.py',arg,str(path),'--out',str(dep/'video_full640'),'--start',str(start),'--frames',str(frames),'--size','640x480','--device','cpu'])
        run('09_codec_full640_'+tag,['continuation_impl/video_codec.py',str(dep/'video_full640'/('heldout_'+tag+'.mp4'))])
manifest={}
for p in sorted(dep.rglob('*')):
    if p.is_file(): manifest[str(p.relative_to(dep))]={'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
(dep/'artifact_hashes.json').write_text(json.dumps(manifest,indent=1))
(dep/'PIPELINE_COMPLETED.json').write_text(json.dumps({'time':datetime.datetime.now().astimezone().isoformat(),'seconds':time.time()-started,
    'numeric_pipeline_completed':True,'artistic_acceptance':'pending independent actual-output review','FPGA':'not synthesized, simulated or board-tested'},indent=2))
print('PIPELINE_COMPLETED',flush=True)
