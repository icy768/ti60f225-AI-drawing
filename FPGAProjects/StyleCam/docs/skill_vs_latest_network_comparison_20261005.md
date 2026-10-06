# 三种开源 Skill 与 StyleCam 最新网络同图对比

日期：2026-10-05

## 输入

同一张真实留出照片：

`audits/v15_v6_restart_20261005/new_scenes_comparisons/city_street_000000026204_input.png`

原始照片来自本地 COCO val2017 留出集，统一预处理为 RGB 640×480。

## Skill 参考流程

本地保存的源码快照位于 `C:/Users/蔡哲涵/Desktop/fpga/风格Skill研究_20261004/sources`：

- Van Gogh：`KShang29/van_gogh_oil_painting_transformation`，MIT，使用其 Van Gogh 约束和推荐的高质量 image-edit 路径；同时实际运行了其本地 CLI 渲染器，结果为 `audits/skill_network_comparison/city_street_vangogh_skill_local.png`。
- Ukiyo-e：`Emily2040/nano-banana-image-skill`，Apache-2.0，使用其 Ukiyo-e 提示模块规则（有限调色板、平涂版块、深色木刻轮廓、受控渐变）。
- 水墨：`lzhandcyx/photo-to-ink-painting-skill`，MIT，使用其照片内容优先、留白、墨色层次、无新增实体、无题款印章规则。

由于后两个仓库是提示/工作流 skill，不是通用照片到照片的离线模型，两个结果使用 skill 规则驱动的 image-edit 工作流生成，原始生成文件已复制到 `audits/skill_network_comparison`。

## StyleCam 对照

StyleCam 对照为当前 v15 候选的同图输出：

- FP32：`audits/v15_v6_restart_20261005/new_scenes_comparisons/*_fp32.png`
- INT8：`audits/v15_v6_restart_20261005/new_scenes_comparisons/*_int8.png`

总拼图：`audits/skill_network_comparison/city_street_skill_vs_stylecam.jpg`

拼图每行依次为：Input、Open-source skill、StyleCam v15 FP32、StyleCam v15 INT8；三行分别是 Van Gogh、Ukiyo-e、Ink。

## 观察

- Skill 参考输出的风格强度更高：梵高的笔触和蓝黄互补更夸张，浮世绘的有限色块与轮廓更清晰，水墨的纸白和外围消散更明显。
- StyleCam v15 保留了原图空间关系和主体，但效果更克制；INT8 与 FP32 的结构一致，INT8 在部分场景中对比度和饱和度略高。
- Skill 结果是视觉参考教师，不是 Ti60/FPGA 推理图；不能把 skill 图的生成质量直接当作板端效果或 PSNR/SSIM 真值。
