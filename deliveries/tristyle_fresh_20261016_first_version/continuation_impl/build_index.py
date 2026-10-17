"""Build an honest delivery index from existing files and recorded actual-output review."""
import argparse, datetime, html, json, pathlib
ROOT=pathlib.Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser();ap.add_argument('--deployment',required=True);ap.add_argument('--selection',required=True);a=ap.parse_args()
dep=ROOT/a.deployment;sel=json.loads((ROOT/a.selection).read_text(encoding='utf-8'))
assert sel.get('actual_output_reviewed') is True, 'Actual output review is required'
required=['PIPELINE_COMPLETED.json','tristyle_v3_fp32.pt','tristyle_v3_int8.ts','tristyle_v3_hw.bin','tristyle_v3_hw.bytes.json','final_numeric_verification.json','hwpack_verification.json','float_native_size/comparison.jpg','normative_integer_comparison.jpg','hardware/HARDWARE_FINAL.md']
missing=[p for p in required if not (dep/p).is_file()]
if missing:raise SystemExit('Missing: '+', '.join(missing))
pack=json.loads((dep/'tristyle_v3_hw.bytes.json').read_text());num=json.loads((dep/'final_numeric_verification.json').read_text())
assert pack['total_bytes']==(dep/'tristyle_v3_hw.bin').stat().st_size<=500000
assert num['scenes']==17
def link(label,p):return f'[{label}]({str(p.resolve()).replace(chr(92),"/")})'
L=['# 三风格网络首版交付索引','',
   '**艺术验收：'+sel['art_verdict']+'**','',sel['selection_reason'],'',
   '可运行与艺术符合度分别验收。下列是实际裸学生推理，未经NPR后处理；教师目标预览不列为学生成果。', '',
   '## 直接查看','',
   '- '+link('同一17场景 × 三风格：同QAT权重FLOAT原尺寸对比',dep/'float_native_size/comparison.jpg'),
   '- '+link('同一17场景 × 三风格：实际规范Q31整数（320×240）',dep/'normative_integer_comparison.jpg')]
for name in ('vangogh','ukiyoe','ink'):L.append('- '+link(name+'：FLOAT / fake-INT8 / oneDNN / Q31并排',dep/f'quant_modes_{name}.jpg'))
if (dep/'preview_7_categories.jpg').exists():L.append('- '+link('七类内容精简预览（实际FLOAT）',dep/'preview_7_categories.jpg'))
for mode in ('fp32','int8','integer_reference'):
    v=dep/'video'/f'heldout_{mode}_h264.mp4'
    if v.exists():L.append('- '+link(mode+'：未训练Sintel动画动作视频，320×240各面板',v))
    v=dep/'video_full640'/f'heldout_{mode}_h264.mp4'
    if v.exists():L.append('- '+link(mode+'：同模型640×480各面板视频（主机离线）',v))
if (dep/'VIDEO_REPORT.md').exists():L.append('- '+link('各后端视频实测、帧数和曲线',dep/'VIDEO_REPORT.md'))
if (dep/'video_temporal_curves.png').exists():L.append('- '+link('实际源帧光流一致性曲线（非艺术评分）',dep/'video_temporal_curves.png'))
L+=['','## 权重和源码','',
    '- '+link('源码、权重、测试结果便携ZIP',ROOT/'release/tristyle_first_version.zip'),
    '- '+link('可直接打开的逐场景HTML查看器',ROOT/'release/INDEX.html'),
    '- '+link('FLOAT可推理权重',dep/'tristyle_v3_fp32.pt'),
    '- '+link('oneDNN可执行INT8 TorchScript',dep/'tristyle_v3_int8.ts'),
    '- '+link(f'全部三风格固定格式整数部署包：{pack["total_bytes"]:,} 字节',dep/'tristyle_v3_hw.bin'),
    '- '+link('字节逐项统计、SHA256',dep/'tristyle_v3_hw.bytes.json'),
    '- '+link('源码、最终依赖与推理/重训练方法',ROOT/'REPRODUCE.md'),
    '- '+link('网络架构',ROOT/'claude_impl/model.py')+' / '+link('训练代码',ROOT/'continuation_impl/train_art.py'),
    '- '+link('数据、教师与许可实测记录',ROOT/'reports/continuation/TEACHERS_AND_LICENSES.md'),
    '- '+link('实际选型及Codex视觉审查',ROOT/a.selection)+' / '+link('逐类艺术缺口',ROOT/'reports/continuation/ART_REVIEW.md'),
    '', '`.pt/.ts`用于主机，固定bin已经包含全部三风格，不需另加权重或元数据。JSON bin是替代格式，不需同时部署。',
    '', '## 验证范围','', '|项目|结论|','|---|---|',
    f'|三风格总包|实测{pack["total_bytes"]:,}B ≤ 500000B，含全部权重/偏置/Q31/图/头/对齐|',
    '|序列化与整数|实际CPU包独立执行；两种包逐像素一致性见记录|',
    '|FP32/fake/INT8|同一QAT checkpoint，17场景实际输出及量化保持度|',
    '|视频|Sintel源动画24fps、未训练动作640+；主机离线，不是摄像头/板卡实测；分辨率与帧数见各视频JSON|',
    '|FPGA|参数化DDR3分析；抽样算术单元RTL功能仿真通过，整网RTL/Efinity/时序/板测未完成，无实际资源/fps|',
    '|640×480 ≥15fps|当前模型未实现；320×240是明确降分辨率方案，也未板测|',
    '', '## 独立视觉验收','']
for name,row in sel['axes'].items():L.append('- **'+name+'：** '+row)
L+=['','## 数字证据','',link('完整量化实测记录',dep/'final_numeric_verification.json')+'；'+link('固定/JSON整数格式校验',dep/'hwpack_verification.json')+'；'+link('DDR3图计数与成本估算',dep/'hardware/HARDWARE_FINAL.md')+'；'+link('抽样算术RTL功能仿真范围',ROOT/'rtl_math/README.md')+'；'+link('全部文件与6视频完整性核验',dep/'delivery_selfcheck.json'),
    '', '|风格|FLOAT对Q31 PSNR|SSIM|','|---|---:|---:|']
for name,row in num['summary'].items():L.append(f'|{name}|{row["FLOAT_vs_native_PSNR"]:.2f}dB|{row["FLOAT_vs_native_SSIM"]:.4f}|')
L+=['','PSNR/SSIM仅衡量相同checkpoint量化保持，不能证明艺术符合度。主机耗时不解释为FPGA吞吐。',
    '', '## 未完成/未验证','',*['- '+s for s in sel['unmet']],
    '', '项目独立性与接手：'+link('独立性记录',ROOT/'INDEPENDENCE.md')+'；'+link('CC恢复失败后用户授权接手证据',ROOT/'supervisor/takeover_20261017_0443.json'),
    '', '生成时间：'+datetime.datetime.now().astimezone().isoformat()]
(ROOT/'final_index.md').write_text('\n'.join(L),encoding='utf-8')
release=ROOT/'release';release.mkdir(exist_ok=True)
# Plain local HTML viewer; all images are real output files, no generative media.
parts=['<!doctype html><meta charset="utf-8"><title>三风格首版</title><style>body{font:16px system-ui;margin:24px;background:#f5f3ed;color:#222}header{max-width:1100px}table{width:100%;table-layout:fixed;border-spacing:12px}img{width:100%;height:auto;display:block}video{width:100%}td{vertical-align:top}article{background:white;padding:14px;margin:18px 0}p{line-height:1.6}</style>',
    '<header><h1>三风格学生网络首版</h1><p><b>艺术验收：'+html.escape(sel['art_verdict'])+'</b></p><p>'+html.escape(sel['selection_reason'])+'</p><p>实际FLOAT输出。点击图片查看原尺寸；<a href="../PORTABLE_INDEX.md">整数与全部验证记录索引</a>。主机离线执行，未实现FPGA15fps。</p></header>']
for p in sorted((ROOT/'data/test').glob('*.png')):
    parts.append('<article><h2>'+html.escape(p.stem)+'</h2><table><tr>')
    imgs=[('input',p)]+[(s,dep/'float_native_size'/f'{p.stem}_{s}.png') for s in ('vangogh','ukiyoe','ink')]
    for label,f in imgs:
        rel='../'+f.relative_to(ROOT).as_posix();parts.append(f'<td>{label}<a href="{rel}"><img loading="lazy" src="{rel}"></a></td>')
    parts.append('</tr></table></article>')
for mode in ('fp32','int8','integer_reference'):
    v=dep/'video'/f'heldout_{mode}_h264.mp4'
    if v.exists():parts.append('<article><h2>'+mode+'：320×240各面板，主机离线推理</h2><video controls preload="metadata" src="../'+v.relative_to(ROOT).as_posix()+'"></video></article>')
    v=dep/'video_full640'/f'heldout_{mode}_h264.mp4'
    if v.exists():parts.append('<article><h2>'+mode+'：640×480各面板，主机离线推理</h2><video controls preload="metadata" src="../'+v.relative_to(ROOT).as_posix()+'"></video></article>')
(release/'INDEX.html').write_text('\n'.join(parts),encoding='utf-8')
print('INDEX_CREATED',ROOT/'final_index.md')
