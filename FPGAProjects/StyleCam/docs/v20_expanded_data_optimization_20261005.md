# StyleCam v20 扩展数据与固定图优化记录

日期：2026-10-05。工作目录：`C:\Users\蔡哲涵\Desktop\fpga\FPGAProjects\StyleCam`。

本轮遵守赛题边界：推理网络仍是 v6/v8 的 C24、Fc16、4 个残差块、3 风格、IN 归一化和深度可分离块；只改训练监督、教师参考和量化感知训练。输入输出仍为 640×480，未增加通道、层或后处理。

## 数据扩充

使用 The Metropolitan Museum of Art 的官方 Collection API（[官方 API 文档](https://metmuseum.github.io/)）。该文档说明其 Open Access 数据和公共领域图像记录；本轮逐条读取 API 的 `isPublicDomain`，下载记录均为 `true`，并保存 API 地址、对象地址、图像地址、字节数和 SHA256。

新增文件在 `dataset_v2/style_references_expanded_20261005/`，共 10 张：浮世绘 3 张（对象 54437、54905、55118），水墨 7 张（45070、45420、45700、42342、42346、42344、49131）。梵高没有声称下载新的博物馆图片，使用已有开放参考库。清单和校验文件分别是 `manifest.json` 与 `SHA256SUMS.txt`。

同时把已安装 Skill 工作流生成的视觉参考加入 `dataset_v2/skill_teacher_expanded_20261005/`：梵高城市笔触、浮世绘城市色块、水墨城市渲染、油画麦田、浮世绘富士和两张水墨输出，共 7 张。它们被标为 `synthetic_skill_teacher`，是风格教师参考，不是成对真值，也不构成对任何艺术作品授权状态的判断。新生成的梵高图来自本地已安装 imagegen Skill，原始文件和复制后的工作区路径都保留在 manifest 中。

## 实际训练

浮点扩展监督使用 `algo/train_art_styles_v19.py`，从 v18 浮点检查点初始化，900 步、batch 4、学习率 `3e-5`、`extra_strength=1.0`、`phase_shift=750`，输出：

`runs/art_styles_c24_v19_expanded_skill/student.pt`

其监督参考池合并了原有参考、10 张 The Met 图片和 7 张 Skill 教师图，并按风格归一化权重。随后用 `algo/train_art_quant_distill.py` 做固定合同下的 QAT：900 步、batch 4、学习率 `2e-5`、`soft_weight=1.0`、`style_weight=0.20`、`gradient_weight=0.35`、浮世绘块内平坦约束 `1.5`、水墨平衡约束 `0.5`。输出：

`runs/art_styles_c24_v20_qat900_soft1/student.pt`

量化合同为 `audits/v20_qat900_export/`，复用并冻结 v19 校准的层尺度和整数 `R/S`，没有改变推理图。

## 图结构和赛题边界核验

核验文件：`audits/v20_graph_vs_v6.json`。

| 项目 | 结果 |
|---|---:|
| C / Fc / 残差块 | 24 / 16 / 4 |
| 参数量 | 11,028 |
| VGA 卷积 MAC | 339,148,800 |
| 输入 / 输出 | `[1,3,480,640]` / `[1,3,480,640]` |
| cfg、风格列表 | 相同 |
| `graph_changed` | `false` |
| 量化合同核验 | `true` |
| 板端核验 | `false`，当前未枚举到明确 Ti60/JTAG/SC431HAI 设备 |

## 24 图同图同尺度量化结果

协议是 24 张留出 RGB VGA 图，比较 v20 INT8 与 v19 浮点教师。PSNR/SSIM 是量化保真诊断，不是对原始照片的艺术质量分数。

| 风格 | INT8 对浮点 PSNR | INT8 对浮点 SSIM | 边缘 F1 | 风格结构指标 |
|---|---:|---:|---:|---|
| 梵高 | 26.43 dB | 0.8970 | 0.9029 | surface detail 0.0482 |
| 浮世绘 | 28.22 dB | 0.8987 | 0.9076 | flat interior 0.1877；boundary gradient 0.1298 |
| 水墨 | 27.00 dB | 0.9010 | 0.8645 | paper 0.8715；subject dark 0.5288；contrast 0.6560 |

完整逐图记录在 `audits/v20_qat900_paired24/summary.json`。相较 v18 QAT，v20 的浮世绘和水墨 INT8 PSNR/SSIM 上升；梵高 PSNR 略低约 0.09 dB，但 SSIM 略高，风格色彩/边缘响应增强。

## Skill 与 v20 的真实同图对照

输入是同一张城市街景 `city_street_000000026204_input.png`。对照图：

`audits/v20_city_skill_comparison/city_street_skill_vs_v20.jpg`

每行依次是输入、Skill 教师、v20 FP32、v20 INT8；单张输出也保存在该目录。量化/视觉差异指标在 `skill_v20_gap_metrics.json`。指标仅用于说明两类输出的差别：生成式 Skill 教师会重构纹理与色块，因此不能当作网络的配对真值。

| 风格 | Skill→v20 FP32 PSNR / SSIM | 观察到的差距 |
|---|---:|---|
| 梵高 | 13.44 dB / 0.185 | v20 已有方向性纹理和互补色，但 Skill 的笔触更长、更连续，亮暗和蓝黄对比更强；v20 INT8 的高频更明显但有量化颗粒。 |
| 浮世绘 | 11.41 dB / 0.160 | v20 能保留轮廓和块状区域，较 v18 更亮；Skill 色块更纯、更亮、块间边界更干净，v20 仍偏暗、饱和度不足。 |
| 水墨 | 9.87 dB / 0.148 | v20 有纸白、浓墨主体和结构边缘，Skill 的纸张扩散、干湿边缘和墨迹层次更丰富；v20 INT8 比浮点更黑、对比更高。 |

这些低 PSNR/SSIM 数值主要反映 Skill 对场景进行的非配准内容重绘，不应解释为 v20 相对原照片的保真度失败。

## 相机序列稳定性

使用已有 PC USB 相机 30 帧原始序列 `audits/v10_region_20261004/pc_camera30/raw`，不是 SC431HAI 实时采集，也不是板端测量。回放结果：

- FP32 v20：梵高对齐帧 MAE 8.62（v18 为 8.29），浮世绘 3.52（v18 为 3.82），水墨 4.40（v18 为 4.67）；CUDA 中位延迟约 4.13 / 4.20 / 4.31 ms。
- 整数 v20：梵高对齐帧 MAE 13.49，浮世绘 7.22，水墨 6.78；这是 CPU golden 整数回放，不能直接当作 FPGA 帧率。完整记录分别在 `audits/v20_camera30_fp32_run/summary.json` 和 `audits/v20_camera30_integer_run/summary.json`。

## 当前结论和下一步

v20 是当前的研究候选：浮世绘的亮度、块内简化和边界分离已改善，水墨的纸白/浓墨空间分离保持，梵高的颜色和边缘响应略增强；网络图、通道、分辨率和 MAC 未变。与 Skill 的差距仍集中在三点：梵高的连续多尺度笔触，浮世绘的纯亮色块和更高整体亮度，水墨的纸张扩散及干湿边缘。PSNR/SSIM 已被纳入量化门槛，但目前没有赛题提供的同领域绝对合格阈值和成对真值，不能据此宣称达到官方指标。

下一轮应先做同图盲评和更长真实相机序列；通过风格、结构和时序门槛后，再做完整 PC 整数/RTL 逐位对拍，最后才进行物理板卡验证。若继续优化，采用单因素监督：梵高增加区域结构方向和笔触连续目标，浮世绘提升亮度/纯度并加强块间轮廓，水墨单独提升纸张扩散与干湿边缘，同时继续冻结图结构和量化合同。
