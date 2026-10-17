"""Report completed actual clips. No new inference, synthesized frames or artistic score."""
import argparse,csv,datetime,hashlib,json,pathlib
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=pathlib.Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser();ap.add_argument('deployment');a=ap.parse_args();dep=ROOT/a.deployment
styles=('vangogh','ukiyoe','ink');modes=('fp32','int8','integer_reference');rows=[]
fig,axes=plt.subplots(3,2,figsize=(12,9),sharex='col',constrained_layout=True)
colors=dict(zip(modes,('#4C78A8','#F58518','#54A24B')))
for col,folder in enumerate(('video','video_full640')):
    data={mode:json.loads((dep/folder/f'video_{mode}_metrics.json').read_text()) for mode in modes}
    frames=[r['frame'] for r in data['fp32']['rows']]
    for mode in modes:
        assert [r['frame'] for r in data[mode]['rows']]==frames
        for left,right in zip(data['fp32']['rows'],data[mode]['rows']):
            if left.get('input_warp_MAE') is not None:assert abs(left['input_warp_MAE']-right['input_warp_MAE'])<1e-9
    for i,style in enumerate(styles):
        ax=axes[i,col]
        for mode in modes:
            d=data[mode];vals=[r.get(style+'_warp_MAE',np.nan) for r in d['rows']]
            ax.plot(frames,vals,color=colors[mode],linewidth=1,label=mode)
            v=np.asarray(vals,float);v=v[np.isfinite(v)];assert len(v)
            rows.append({'size':'x'.join(map(str,d['summary']['size'])),'style':style,'backend':mode,
                'frames':len(frames),'first_frame':frames[0],'last_frame':frames[-1],'valid_pairs':len(v),
                'MAE_mean':float(v.mean()),'median':float(np.median(v)),'p95':float(np.quantile(v,.95)),
                'host_ms_mean':d['summary'][style]['host_ms_mean'],'model_sha256':d['summary']['model_sha256']})
        baseline=[r.get('input_warp_MAE',np.nan) for r in data['fp32']['rows']]
        baseline=[np.nan if r is None else r for r in baseline]
        ax.plot(frames,baseline,color='#777777',linestyle=':',linewidth=.9,label='input')
        ax.set_title(style+' / '+('320x240' if col==0 else '640x480'));ax.grid(alpha=.2);ax.set_ylim(bottom=0)
        if col==0:ax.set_ylabel('masked RGB warp MAE [0,1]')
        if i==2:ax.set_xlabel('original source frame index')
        if i==0:ax.legend(fontsize=8,ncol=2)
fig.suptitle('Heldout Sintel: measured input-flow consistency (not art quality or FPGA timing)',fontsize=12)
fig.savefig(dep/'video_temporal_curves.png',dpi=180);fig.savefig(dep/'video_temporal_curves.svg');plt.close(fig)
with (dep/'video_summary.csv').open('w',newline='',encoding='utf-8-sig') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
record={'time':datetime.datetime.now().astimezone().isoformat(),'status':'MEASURED summaries of completed actual inference clips',
    'pack_sha256':hashlib.sha256((dep/'tristyle_v3_hw.bin').read_bytes()).hexdigest(),'rows':rows,
    'method':'Original input backward-Farneback flow and photometric/visibility mask; scene cuts omitted. Per-pair masked RGB MAE, unweighted mean of valid pairs.',
    'limits':['Source24fps animation, not camera30fps or FPGA test.','Short clips do not establish long-time stability.',
        'Smooth/desaturated output may lower MAE; this is not artistic ranking.','Original letterbox pixels are included by the existing mask; no post-hoc ROI cherry-picking.']}
(dep/'video_summary.json').write_text(json.dumps(record,indent=1))
L=['# 视频实测汇总','',record['status'],'','Sintel为Blender Foundation CC BY3.0动画，不是摄像头或板卡实测。所有后端使用相同源帧、缩放、光流和掩码；逐帧input_warp_MAE一致性已校验。','',
   '|尺寸|风格|后端|帧区间/帧数|有效对|MAE均值|P95|主机ms/风格帧|','|---|---|---|---|---:|---:|---:|---:|']
for r in rows:L.append(f'|{r["size"]}|{r["style"]}|{r["backend"]}|{r["first_frame"]}–{r["last_frame"]}/{r["frames"]}|{r["valid_pairs"]}|{r["MAE_mean"]:.5f}|{r["p95"]:.5f}|{r["host_ms_mean"]:.2f}|')
L+=['','主机耗时受CPU/并行任务影响，不是FPGA帧率。masked warp MAE按有效帧对非加权平均；源片黑边也按原掩码参与。低误差可能来自平滑/去色，不证明笔触、语义正确或长时稳定。','',
    '曲线video_temporal_curves.png/.svg，逐帧数据在video/和video_full640/。视频按源片24fps播放，不把离线处理速度伪报成实时性能。']
(dep/'VIDEO_REPORT.md').write_text('\n'.join(L),encoding='utf-8');print('VIDEO_SUMMARY_COMPLETED',len(rows))
