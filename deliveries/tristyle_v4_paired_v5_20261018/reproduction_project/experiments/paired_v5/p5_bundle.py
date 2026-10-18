"""Build a standalone inference/evidence bundle only after full retention finishes."""
from pathlib import Path
import datetime as dt
import hashlib
import html
import json
import shutil
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[2]
P5=ROOT/'reports/paired_v5/P5'
D=ROOT/'deployment/paired_v5_qat600_export01'
V=P5/'retention_export01'


def copy(source,dest):
    dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)


def main():
    assert (V/'RESULT.json').exists(),'Full fixed17 retention has not completed'
    result=json.loads((V/'RESULT.json').read_text());assert len(result['rows'])==102
    out=ROOT/'release/paired_v5_20261018';out.mkdir(exist_ok=False,parents=True)
    runtime=out/'runtime';runtime.mkdir()
    for name in ['model.py','graph.py','quantize.py','int_ref.py','int_contract.py','hwpack.py']:
        copy(ROOT/'baseline/source/claude_impl'/name,runtime/name)
    copy(ROOT/'experiments/paired_v5/consistent_qat.py',runtime/'consistent_qat.py')
    copy(ROOT/'experiments/paired_v5/portable_infer.py',out/'infer.py')
    for name in ['fp32.pt','fake_int8_state.pt','int8.ts','all_styles_hw.bin','input_scales.json']:
        copy(D/name,out/'models'/name)
    # Training/reproduction sources retain their project-relative layout.
    repro=out/'reproduction_project'
    for folder in ['baseline/source','experiments/paired_v5','diagnostics']:
        base=ROOT/folder
        for p in base.rglob('*.py'):
            if folder=='experiments/paired_v5' and len(p.relative_to(base).parts)>1:continue
            if '__pycache__' not in p.parts:copy(p,repro/p.relative_to(ROOT))
    for name in ['baseline/manifest.json','data/fixed_test_manifest.json','data/curated_references_v3.json']:
        copy(ROOT/name,repro/name)
    for run in ['claude_p3r2_ukiyoe','claude_p3r2_vangogh','claude_p3r2_ink','claude_p4_vangogh_v7']:
        for name in ['config.json','finished.json']:
            path=ROOT/'experiments/paired_v5'/run/name
            if path.exists():copy(path,repro/'experiments/paired_v5'/run/name)
    for run in ['paired_v5_qat600_01','paired_v5_qat600_export01']:
        base=ROOT/'deployment'/run
        for name in ['config.json','qat_metrics.jsonl','input_scales.json','calibration_bounds.json','RESULT.json']:
            if (base/name).exists():copy(base/name,out/'provenance'/run/name)
        if (base/'source').exists():shutil.copytree(base/'source',out/'provenance'/run/'source')
    copy(P5/'FREEZE.json',out/'provenance/FREEZE.json')
    copy(D/'hardware_pack_bytes.json',out/'evidence/package_bytes.json')
    copy(V/'RESULT.json',out/'evidence/retention.json')
    copy(P5/'REVIEW.md',out/'evidence/P5_REVIEW.md')
    copy(ROOT/'reports/paired_v5/P3/G2_REVIEW.md',out/'evidence/G2_REVIEW.md')
    for mode in ['native','internal320x240_REDUCED_RESOLUTION']:
        shutil.copytree(V/mode,out/'images'/mode)
    entries=json.loads((ROOT/'data/fixed_test_manifest.json').read_text())
    for name,meta in entries.items():copy(Path(meta['path']),out/'inputs'/name)
    for mode in ['native640','reduced320']:
        src=P5/'videos_fp32_01'/mode
        for name in ['vangogh.mp4','ukiyoe.mp4','ink.mp4','metrics.json']:
            copy(src/name,out/'videos'/mode/name)
    copy(P5/'videos_fp32_01/RESULT.json',out/'evidence/video.json')
    copy(P5/'HARDWARE_COSTS.json',out/'evidence/HARDWARE_COSTS.json')
    (out/'requirements.txt').write_text('torch==2.7.1\nnumpy\nPillow\n',encoding='utf8')
    (out/'README.md').write_text('''# Paired V5 frozen candidate (2026-10-18)\n\n三风格艺术G2未通过，不能作为“各方面明显优于V3”的已验收升级。梵高仍有塑料/机械流纹和肤色问题；浮世绘细结构丢失、轮廓碎，native视频warp比值仍>1.3；水墨仍灰度/蚀刻，干湿组织不足。V3与用户认可水墨基线继续保留。\n\n## Inference\n\nUse Python3.10 and dependencies in requirements.txt. No V3 directory or dataset is needed for inference.\n\n```powershell\npython infer.py --input inputs/person_face.png --output output_integer --backend integer --mode reduced320\npython infer.py --input inputs/person_face.png --output output_fp32 --backend fp32 --mode native\npython infer.py --input inputs/person_face.png --output output_fake --backend fake --mode reduced320\npython infer.py --input inputs/person_face.png --output output_onednn --backend onednn --mode reduced320\n```\n\nOutput directories must not exist. `--style all` (default) or vangogh/ukiyoe/ink. `integer` reads only all_styles_hw.bin and executes the normative CPU integer interpreter; oneDNN uses int8.ts. Different rounding contracts can produce different pixels.\n\nreduced320 means internal320x240, then optional display640x480 bilinear2x. It is a reduced-resolution mode, not native VGA; non4:3 inputs are stretched. Native mode preserves source dimensions with replicate-padding to multiples of8.\n\n## Bytes and hardware\n\n420993 parameters =413664 weights+7329 biases. INT8 weights plus INT32 biases occupy442980B. Complete three-style fixed integer package495552B includes quantization constants, graph/header, descriptors and padding. Do not add the alternative compressed pack to this deployment.\n\nNo whole-network RTL, Efinity synthesis or board FPS evidence. DDR/MAC estimates are in evidence/HARDWARE_COSTS.json, not achieved throughput. VGA>=15fps remains unachieved/unverified. The integer interpreter is a functional reference, not a performance model.\n\n## Evidence and reproduction\n\nINDEX.html shows same-QAT-weight FP32/fake/normative integer outputs on17 inference-only scenes and6 final FP32 videos. Videos are FP32, not normative-integer video. Retention PSNR/SSIM against same checkpoint is distinct from art quality. No photo PSNR is used to promote art.\n\nprovenance holds training/QAT configurations, source snapshots, calibration and export recovery. reproduction_project contains paired-route source/configs; training additionally requires the authorized content/teacher/video data and original manifests at their recorded paths. This is a portable inference bundle, not a bundled training dataset. External path references in provenance are historical and are not accessed by infer.py.\n\nExport recovery reconciled CPU/GPU quantizer scale caches without retraining or modifying saved FP32 weights. Failed original export and experiments remain in the project.\n''',encoding='utf8')
    blocks=['<!doctype html><meta charset="utf-8"><title>Paired V5 frozen candidate</title><style>body{font:16px sans-serif;margin:24px;background:#eee}.grid{display:grid;grid-template-columns:repeat(3,1fr)}img,video{max-width:100%}figure{margin:8px}section{background:white;padding:12px;margin:20px 0}strong{color:#a21c18}</style>',
      '<h1>Paired V5 frozen candidate</h1><p><strong>ARTISTIC G2 FAIL. No FPGA board FPS. Not an accepted V3 upgrade.</strong></p><p><a href="README.md">Usage / limitations</a> · <a href="evidence/retention.json">102 same-checkpoint retention measurements</a> · <a href="evidence/G2_REVIEW.md">Art review</a></p>']
    for mode in ['native','internal320x240_REDUCED_RESOLUTION']:
        blocks.append('<h2>'+mode+'</h2>')
        for name in entries:
            stem=Path(name).stem;blocks.append('<section><h3>'+html.escape(name)+'</h3><details><summary>Input</summary><img loading="lazy" src="inputs/'+name+'"></details>')
            for backend in ['fp32','fake','integer']:
                blocks.append('<h4>'+backend+'</h4><div class="grid">')
                for style in ['vangogh','ukiyoe','ink']:
                    url=f'images/{mode}/{stem}_{style}_{backend}.png';blocks.append(f'<figure><a href="{url}"><img loading="lazy" src="{url}"></a><figcaption>{style}</figcaption></figure>')
                blocks.append('</div>')
            blocks.append('</section>')
    blocks.append('<h2>Final same-QAT FP32 videos (not integer videos)</h2>')
    for mode in ['native640','reduced320']:
        blocks.append('<h3>'+mode+'</h3><div class="grid">')
        for style in ['vangogh','ukiyoe','ink']:blocks.append(f'<figure>{style}<video controls preload="none" src="videos/{mode}/{style}.mp4"></video></figure>')
        blocks.append('</div>')
    (out/'INDEX.html').write_text('\n'.join(blocks),encoding='utf8')
    files=[{'path':p.relative_to(out).as_posix(),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(out.rglob('*')) if p.is_file()]
    (out/'MANIFEST.json').write_text(json.dumps({'created':dt.datetime.now().astimezone().isoformat(),'artistic_passed':False,'files':files},indent=2),encoding='utf8')
    archive=out.with_suffix('.zip')
    assert not archive.exists()
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=5) as z:
        for p in sorted(out.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(out))
    (P5/'BUNDLE_CREATED.json').write_text(json.dumps({'directory':str(out),'zip':str(archive),'bytes':archive.stat().st_size,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'files':len(files)+1,'verification':'pending independent extraction/CRC/hash/links/inference'},indent=2),encoding='utf8')
    print(str(archive),flush=True)


if __name__=='__main__':main()
