# StyleCam v18 逐步优化与验证记录（2026-10-05）

## 结论

当前保留候选为 `runs/art_styles_c24_v18_qat900/student.pt`，对应浮点训练模型 `runs/art_styles_c24_v18_ukiyoe_tone/student.pt` 和独立整数参数 `audits/v18_qat900_export`。v18 只改变训练监督，没有改变 v6 推理网络：13 层、11,028 参数、640×480 输入输出、VGA 卷积 MAC=339,148,800。`audits/v18_graph_vs_v6.json` 已核验 `graph_changed=false`、`quantization_validated=true`；板端尚未连接验证，`board_validated=false`。

## 实际修改

- 新增 `algo/train_art_styles_v16.py`：加入多尺度表面统计、梵高高频/色调监督、浮世绘边界监督、水墨纸白/浓墨/干笔监督。
- 新增 `algo/train_art_styles_v17.py`：把浮世绘的高频目标改为块内局部色彩变化惩罚，单独保留边界对比目标。
- 新增 `algo/train_art_styles_v18.py`：在 v17 块内平坦监督上提高浮世绘参考色调和色彩统计权重，针对开源样例亮度不足的问题。
- 所有新增项都位于训练损失，未向 TinyStyleNet 添加层、通道、算子或后处理。

## 训练命令

```powershell
python algo\\train_art_styles_v16.py --init runs\\art_styles_c24_v15_flat5_qat900_calibrated\\student.pt --out runs\\art_styles_c24_v16_all --steps 900 --batch 4 --lr 6e-5 --variant all --extra-strength 1.0 --phase-shift 750
python algo\\train_art_styles_v17.py --init runs\\art_styles_c24_v16_all\\student.pt --out runs\\art_styles_c24_v17_ukiyoe_flat --steps 900 --batch 4 --lr 4e-5 --variant ukiyoe --extra-strength 1.0 --phase-shift 750
python algo\\train_art_styles_v18.py --init runs\\art_styles_c24_v17_ukiyoe_flat\\student.pt --out runs\\art_styles_c24_v18_ukiyoe_tone --steps 600 --batch 4 --lr 3e-5 --variant ukiyoe --extra-strength 1.0 --phase-shift 750
python algo\\make_qparams.py --checkpoint runs\\art_styles_c24_v18_ukiyoe_tone\\student.pt --out audits\\v18_qparams_24 --count 24
python algo\\train_art_quant_distill.py --init runs\\art_styles_c24_v18_ukiyoe_tone\\student.pt --contract audits\\v18_qparams_24 --out runs\\art_styles_c24_v18_qat900 --steps 900 --batch 4 --lr 2e-5 --soft-weight 0.6 --style-weight 0.35 --gradient-weight 0.35 --ukiyo-hard-flat-weight 1.5 --ink-balance-weight 0.5 --ink-reference runs\\art_styles_c24_v18_ukiyoe_tone\\student.pt
```

## 24 图 INT8 结果

来自 `audits/v18_qat900_paired24/summary.json`。参考是同一 v18 浮点模型；PSNR/SSIM 只表示量化后对自身艺术输出的保持程度，不能替代官方质量阈值。

| 风格 | INT8 对 v18 FP32 PSNR | SSIM | INT8 结构结果 |
|---|---:|---:|---|
| 梵高 | 26.51 dB | 0.8964 | edge F1 0.902；surface detail 0.050 |
| 浮世绘 | 27.76 dB | 0.8966 | edge F1 0.901；块内平坦 0.181；边界梯度 0.133 |
| 水墨 | 26.64 dB | 0.9000 | edge F1 0.868；纸白 0.876；主体暗度 0.539；前景/背景对比 0.665 |

INT8 对自身 FP32 的 SSIM 为梵高 0.849、浮世绘 0.852、水墨 0.856。此前 v15 的对应量化结果约为 0.818、0.817、0.812，因此量化保持性有实际提升。

## 真实相机序列

对已有 USB 相机 30 帧原始序列执行了 FP32 CUDA 和整数 golden replay：

- `audits/v18_camera30_fp32/summary.json`：v18 与 v15 的对齐 MAE（255 制）分别为梵高 8.29/8.31、浮世绘 3.82/3.75、水墨 4.67/4.51；输入帧完全相同，平均有效区域 0.8577。
- `audits/v18_camera30_integer/summary.json`：整数回放对齐 MAE 为梵高 13.42、浮世绘 7.52、水墨 7.05。CPU golden 中位延迟约 199–202 ms，这不是 FPGA 延迟。

## 同图视觉实例

`audits/v18_city_skill_comparison/city_street_skill_vs_v18.jpg` 包含同一城市街景的 Input、三个开源风格 Skill、v18 FP32 和 v18 INT8。v18 已能稳定输出三类风格并保持公交车、建筑和道路位置；与 Skill 仍存在明显差距：Skill 的梵高笔触更长且方向更连续，浮世绘色块更亮更纯、轮廓更硬，水墨的纸张扩散和干湿边缘更丰富。v18 的 INT8 输出比 FP32 更锐，但不能把量化噪声当作真实笔触。

## 尚未达到的目标与下一步

1. 风格特征优先级已经覆盖：梵高表面高频与边缘、浮世绘块内平坦/块间轮廓/亮度、 水墨纸白/浓墨/区域对比/干笔。
2. v18 浮世绘亮度和输入 PSNR/SSIM 相对 v17 上升，但 8 图块内平坦度从 0.191 降到 0.179，仍需在更大留出集上做平坦度与亮度的权衡筛选。
3. 当前 PSNR/SSIM 没有官方同图真值阈值；报告中的数值是量化保持性和输入保真诊断，不能宣称“达到行业合格线”。
4. 需要拿到 Ti60/JTAG/SC431HAI 后，才能完成板端逐帧对拍、时序和真实传感器验证。
