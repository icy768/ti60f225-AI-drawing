"""Build a local evidence index; never infer art acceptance from metrics."""
from pathlib import Path
import html,json
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'reports/paired_v5'
def main():
    blocks=['<!doctype html><meta charset="utf-8"><title>配对V5实验索引</title><style>body{font:16px sans-serif;max-width:1280px;margin:30px auto;background:#eee;color:#222}img{max-width:100%;height:auto}section{padding:18px;background:white;margin:20px 0}a{color:#14539a}summary{cursor:pointer;padding:8px}strong{color:#a21c18}</style>',
        '<h1>配对V5：实际实验与目标对照</h1><p><strong>G1尚未通过；没有新模型晋级。</strong>教师预览与学生网络输出分开列示。所有艺术判断见REVIEW，指标不代替视觉验收。</p>',
        '<p>'+ ' · '.join(f'<a href="{phase}/REVIEW.md">{phase} REVIEW</a>' for phase in ('P0','P1','P1b','P2','P3'))+' · <a href="CLAUDE_ACK.md">指引逐项回应</a></p>']
    for run in sorted((OUT/'P1b').glob('*')):
        if not run.is_dir():continue
        steps=sorted(p for p in run.iterdir() if p.is_dir() and p.name.isdigit())
        if not steps:continue
        last=steps[-1];imgs=sorted(last.rglob('*page*.jpg'))
        if not imgs:continue
        blocks.append(f'<section><h2>学生诊断：{html.escape(run.name)}</h2><p>当前图步数：{last.name}；不代表训练已完成，不是晋级候选。</p>')
        for im in imgs:
            url=im.relative_to(OUT).as_posix();blocks.append(f'<details><summary>{html.escape(str(im.relative_to(last)))}</summary><a href="{url}"><img loading="lazy" src="{url}"></a></details>')
        blocks.append('</section>')
    blocks.append('<h2>离线教师目标预览（不是学生效果）</h2>')
    for folder in sorted((OUT/'P1').glob('targets_*'),reverse=True):
        if not (folder/'preview_manifest.json').exists():continue
        blocks.append(f'<section><h3>{folder.name} — 未通过G1</h3><p><a href="P1/{folder.name}/params.json">参数</a> · <a href="P1/{folder.name}/teacher_assets.json">来源</a></p>')
        for im in sorted(folder.glob('contact_*.jpg')):
            url=im.relative_to(OUT).as_posix();blocks.append(f'<details><summary>{im.name}：INPUT / VG教师 / UK教师 / INK教师</summary><a href="{url}"><img loading="lazy" src="{url}"></a></details>')
        blocks.append('</section>')
    (OUT/'INDEX.html').write_text('\n'.join(blocks),encoding='utf-8')
    print(OUT/'INDEX.html')
if __name__=='__main__':main()
