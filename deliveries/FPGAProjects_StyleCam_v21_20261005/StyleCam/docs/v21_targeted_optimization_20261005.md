# StyleCam v21 针对性强化结果

日期：2026-10-05。

本轮按修订后的 v21 计划先执行单因素监督，没有把新的 FNS 教师直接加入全量蒸馏。训练只修改监督和权重，推理图仍冻结为 v6/v8 图。

## 实际修改

新增 `algo/train_art_styles_v21.py`，在 v19 扩展参考池基础上加入训练期目标：

- 梵高：RGB/色度目标扩张、方向项、局部高频目标下限、亮度对比目标和笔触连续项。
- 浮世绘：亮度偏移、调色板色度扩张、块内平坦项、块间轮廓和边界梯度项。
- 新增的 `export_frozen_qparams.py` 用于导出 QAT 权重，同时冻结已标定的整数 `R/S` 合同。

本轮没有再次下载图片：已有 The Met Open Access/公共领域参考和 Skill 教师图已覆盖这两个风格，所有来源和 SHA256 已在 v19/v20 manifest 中保存。

## 浮点单因素结果

基线是 `runs/art_styles_c24_v19_expanded_skill/student.pt`，8 张留出图、同尺度评估。

| 候选 | 梵高 surface / edge-F1 | 浮世绘 flat / edge-F1 | 浮世绘亮度均值 | 结论 |
|---|---:|---:|---:|---|
| v19 基线 | 0.0399 / 0.8869 | 0.1976 / 0.9138 | 93.1 | 基线 |
| v21c 梵高强化 | 0.0434 / 0.8876 | 0.1605 / 0.9064 | 90.4 | 梵高纹理提升，但共享权重影响浮世绘，未作为最终模型 |
| v21b 浮世绘强化 | 0.0424 / 0.8894 | 0.2653 / 0.9221 | 104.4 | 最佳单模型平衡点 |
| v21 组合浮点 | 0.0411 / 0.8889 | 0.2456 / 0.9196 | 101.5 | 两风格均提升，但量化后保真下降较大 |

v21b 的浮世绘输入 PSNR/SSIM 为 **14.83 dB / 0.4812**，高于 v19 的 14.49 dB / 0.4627。梵高 v21c 的 surface detail 从 0.0399 提到 0.0434，梯度均值从 25.55 提到 27.28，但仍没有达到 edge-F1 0.90 的冲刺目标。

## QAT 结果和最终选择

最终选择：

- 浮点：[v21b_ukiyoe_color_block/student.pt](../runs/art_styles_c24_v21b_ukiyoe_color_block/student.pt)
- INT8：[v21b_ukiyoe_qat900_soft15/student.pt](../runs/art_styles_c24_v21b_ukiyoe_qat900_soft15/student.pt)
- 合同：[v21b_ukiyoe_qat900_soft15_export](../audits/v21b_ukiyoe_qat900_soft15_export.json)

24 张留出图的 INT8 结果，参考是 `v21b_ukiyoe_color_block/student.pt` 的 FP32 输出（SHA256 `053c88a13198669e0c4e6684a923ce2472b8762ead139f1321cf4faa147f654f`）。评估器中 `*_vs_v10` 是历史字段名，不能按字段名误判为 v10 模型：

| 风格 | INT8 对浮点 PSNR | INT8 对浮点 SSIM | edge-F1 | 风格指标 |
|---|---:|---:|---:|---|
| 梵高 | 25.14 dB | 0.8851 | 0.9043 | surface detail 0.0527 |
| 浮世绘 | 27.20 dB | 0.8867 | 0.9168 | flat interior 0.2286；boundary gradient 0.1436 |
| 水墨 | 26.29 dB | 0.8901 | 0.8604 | paper 0.8830；subject dark 0.5218；contrast 0.6527 |

浮世绘第一次 QAT 的块内平坦性曾降到 0.1545，因此被淘汰；提高软输出保持和硬块面约束后回升到 0.2286。自身 INT8 SSIM 为梵高 0.8435、浮世绘 0.8445、水墨 0.8518，梵高/浮世绘相对 v20 分别下降约 0.0033/0.0041，仍在本轮设定的 0.005 回退限制内。组合模型 QAT 的两种风格自身 SSIM 更低，因此没有选用。

## 相同城市图片对照

真实对照图：[city_street_skill_vs_v21b.jpg](../audits/v21_selected_city_comparison/city_street_skill_vs_v21b.jpg)。每行依次是输入、Skill 教师、v21b FP32、v21b INT8。

Skill 仍然更鲜艳、笔触更长、浮世绘色块更纯；v21b 已比 v20 更亮，块面和轮廓更清楚，INT8 梵高的高频纹理也更明显。Skill 图是合成风格教师，不是成对真值，因此不能用 Skill 对齐 PSNR/SSIM 作为官方质量分数。

## 相机与图合同

使用已有 PC USB 相机 30 帧回放，结果文件：

- FP32：`audits/v21b_ukiyoe_camera30_fp32/summary.json`
- 整数 golden：`audits/v21b_ukiyoe_camera30_integer/summary.json`

v21b FP32 的梵高/浮世绘/水墨对齐帧 MAE 为 9.25 / 3.39 / 4.50；v20 为 8.62 / 3.52 / 4.40。浮世绘时序改善，梵高和水墨略有波动，尚不能称为时序全面提升。

图核验：[v21b_ukiyoe_graph_vs_v6.json](../audits/v21b_ukiyoe_graph_vs_v6.json)：13 层、11,028 参数、339,148,800 VGA MAC、640×480 输入输出、`graph_changed=false`、量化合同有效；板端仍未验证。

## 当前判断

v21b 是当前可继续验证的研究候选，优先解决了你指出的浮世绘暗灰、块面不清问题，同时梵高的 INT8 高频/边缘有所提升。梵高的连续笔触和强对比仍未达到 Skill 水平，下一步应继续做内容对齐的离线 FNS 教师小试，而不是继续无目标地放大统一风格权重。完整机器可读记录在 `audits/v21_targeted_optimization_summary.json`。
