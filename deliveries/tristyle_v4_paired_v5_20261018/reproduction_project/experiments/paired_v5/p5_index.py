"""Build an honest local P5 index from completed or explicitly partial evidence."""
from pathlib import Path
import hashlib
import html
import json
import os

ROOT=Path(__file__).resolve().parents[2]
P5=ROOT/'reports/paired_v5/P5'
D=ROOT/'deployment/paired_v5_qat600_export01'
V=P5/'retention_export01'


def relative(path):return os.path.relpath(path,P5).replace('\\','/')


def main():
    complete=(V/'RESULT.json').exists()
    result=json.loads((V/'RESULT.json').read_text()) if complete else None
    entries=json.loads((ROOT/'data/fixed_test_manifest.json').read_text())
    blocks=['<!doctype html><meta charset="utf-8"><title>Paired V5 P5 evidence</title>',
       '<style>body{font:16px sans-serif;margin:24px;background:#eee}.grid{display:grid;grid-template-columns:repeat(3,1fr)}figure{margin:6px}img{max-width:100%;height:auto}section{background:white;padding:10px;margin:20px 0}strong{color:#a21c18}video{max-width:100%}</style>',
       '<h1>Paired V5: same-QAT FP32 / fake / normative integer</h1>',
       '<p><strong>ARTISTIC G2 FAIL. No FPGA synthesis or board FPS measurement. Not an accepted V3 upgrade.</strong></p>',
       '<p>VG v7 / UK r2 / ink r2 frozen 03:00; 600-step preservation QAT completed. Export repaired by CPU scale-cache reconciliation without retraining or changing FP32 weights.</p>',
       '<p><a href="FREEZE.json">Freeze / art deficits</a> · <a href="REVIEW.md">P5 review</a> · <a href="../P3/G2_REVIEW.md">G2 review</a> · <a href="../P4/g2_selected_v7_v2/INDEX.html">V3 vs pre-QAT actual three-style outputs</a></p>',
       '<p>Retention status: '+('all 102 cases completed' if complete else '<strong>IN PROGRESS: partial saved cases only; do not infer full retention passed</strong>')+'</p>']
    if result:
        blocks.append('<p><a href="retention_export01/RESULT.json">Full retention measurements</a></p><pre>'+html.escape(json.dumps(result['summary'],indent=2))+'</pre>')
    else:
        blocks.append('<p><a href="retention_export01/progress.json">Current progress</a></p>')
    for mode in ['native','internal320x240_REDUCED_RESOLUTION']:
        blocks.append('<h2>'+mode+'</h2><p>'+('Original variable input dimensions, replicate-padding to8 and crop back.' if mode=='native' else '320x240 internal reduced-resolution mode. PNGs are internal resolution; any browser enlargement adds no native detail.')+'</p>')
        for name in entries:
            blocks.append('<section><h3>'+html.escape(name)+'</h3>')
            for style in ['vangogh','ukiyoe','ink']:
                blocks.append('<h4>'+style+'</h4><div class="grid">')
                for backend in ['fp32','fake','integer']:
                    path=V/mode/f'{Path(name).stem}_{style}_{backend}.png'
                    if path.exists():
                        url=relative(path);blocks.append(f'<figure><a href="{url}"><img loading="lazy" src="{url}"></a><figcaption>{backend}</figcaption></figure>')
                    else:blocks.append(f'<figure>{backend}: pending</figure>')
                blocks.append('</div>')
            blocks.append('</section>')
    blocks.append('<h2>Held-out final same-QAT FP32 videos (not integer videos)</h2>')
    video_root=P5/'videos_fp32_01'
    for mode in ['native640','reduced320']:
        blocks.append('<h3>'+mode+'</h3>')
        for style in ['vangogh','ukiyoe','ink']:
            path=video_root/mode/(style+'.mp4')
            if path.exists():blocks.append(f'<p>{style}</p><video controls preload="none" src="{relative(path)}"></video>')
            else:blocks.append('<p>'+style+': pending</p>')
    manifest=[]
    for path in sorted(D.glob('*')):
        if path.is_file():manifest.append({'path':relative(path),'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    summary={'parameter_count':420993,'parameter_storage_INT8weight_INT32bias_bytes':442980,
             'complete_fixed_deployment_package_bytes':(D/'all_styles_hw.bin').stat().st_size,
             'retention_complete':complete,'artistic_G2_passed':False,'FPGA_measured':False,'files':manifest}
    (P5/'ARTIFACTS.json').write_text(json.dumps(summary,indent=2),encoding='utf8')
    blocks.append('<p><a href="ARTIFACTS.json">Artifact hashes / distinct parameter and package byte counts</a></p>')
    (P5/'INDEX.html').write_text('\n'.join(blocks),encoding='utf8')
    print(json.dumps({'index':str(P5/'INDEX.html'),'retention_complete':complete,'deployment_files':len(manifest)}))


if __name__=='__main__':main()
