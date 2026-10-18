"""Final same-QAT-weight FP32 held-out videos, two modes, six style clips."""
from pathlib import Path
import hashlib
import json
import cv2
import g2_video

ROOT=Path(__file__).resolve().parents[2]


def main():
    assert json.loads(Path('D:/ClaudeTest/guidance/OWNER.json').read_text(encoding='utf-8-sig'))['owner']=='codex'
    cv2.setNumThreads(1)
    checkpoint=ROOT/'deployment/paired_v5_qat600_export01/fp32.pt'
    cache=ROOT/'data/paired_v5/g2_video_640_789_cache'
    root=ROOT/'reports/paired_v5/P5/videos_fp32_01';root.mkdir(exist_ok=False)
    (root/'source.py').write_bytes(Path(__file__).read_bytes())
    (root/'source_g2_video.py').write_bytes(Path(g2_video.__file__).read_bytes())
    summary={}
    for mode in ['native640','reduced320']:
        out=root/mode
        g2_video.evaluate(cache,checkpoint,out,mode,'cuda')
        cap=cv2.VideoCapture(str(out/'heldout.mp4'));assert cap.isOpened()
        fps=cap.get(cv2.CAP_PROP_FPS)
        writers=[cv2.VideoWriter(str(out/(style+'.mp4')),cv2.VideoWriter_fourcc(*'mp4v'),fps,(640,480)) for style in ['vangogh','ukiyoe','ink']]
        assert all(w.isOpened() for w in writers)
        count=0
        while True:
            ok,frame=cap.read()
            if not ok:break
            assert frame.shape[:2]==(480,2560)
            for i,w in enumerate(writers):w.write(frame[:,640*(i+1):640*(i+2)].copy())
            count+=1
        cap.release()
        for w in writers:w.release()
        assert count==150
        metrics=json.loads((out/'metrics.json').read_text())
        baseline=ROOT/'reports/paired_v5/P3'/('video_V3_native640_r2' if mode=='native640' else 'video_V3_reduced320')/'metrics.json'
        base=json.loads(baseline.read_text())
        assert metrics['cache_manifest_sha256']==base['cache_manifest_sha256']
        summary[mode]={s:{'warp_ratio_vs_V3':metrics['summary'][s]['warp_MAE_mean']/base['summary'][s]['warp_MAE_mean'],
                          'pairs':metrics['summary'][s]['pairs']} for s in ['vangogh','ukiyoe','ink']}
    (root/'RESULT.json').write_text(json.dumps({'checkpoint_sha256':hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
        'summary':summary,'frames_per_video':150,'style_clips':6,
        'backend':'same-QAT FP32 only, not normative integer video',
        'clips':'Decoded montage crops re-encoded as MP4; lossy display only. Raw warp metrics computed before encoding.',
        'artistic_passed':False,'FPGA_fps_measured':False},indent=2))
    print('FINAL_FP32_VIDEO_COMPLETE',flush=True)


if __name__=='__main__':main()
