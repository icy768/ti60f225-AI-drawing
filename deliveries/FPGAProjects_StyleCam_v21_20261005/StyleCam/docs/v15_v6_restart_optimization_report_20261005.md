# StyleCam v6 回退与监督优化记录（2026-10-05）

## 目标排序

1. **P0 系统与推理图边界**：保持 v6 的 `C=24/Fc=16/n_res=4/block=dw1/IN`、三通道、640×480 输入输出、339,148,800 VGA 卷积 MAC；训练期监督不得引入推理期算子。
2. **P1 风格辨识与主体可读性**：梵高要有连续方向笔触；浮世绘要有块内简化和块间深轮廓；水墨要有主体浓墨、背景纸白和边缘消散。
3. **P2 整数部署一致性**：固定硬件算术合同，重新标定新权重的 R/S 和 IN 系数，再做整数 golden 对拍。
4. **P3 PSNR/SSIM**：在 P1/P2 通过后提高同一参考、同一分辨率、同一量化合同下的 PSNR/SSIM。赛题未给绝对阈值，本文内部筛选线约为 25 dB、0.85 SSIM，不能代替官方阈值。
5. **P4 实时与切换**：PC 30 帧代理时序已测；SC431HAI、Ti60、DDR/HDMI、帧率和无丢帧仍需板端测量。
6. **P5 轻量化与资源**：不增加通道、层、分支或推理后处理；当前 11,028 参数和原 MAC 预算不变。
7. **P6 展示交互**：在前述目标通过后接入风格切换、FPS 和 OSD。

## 已执行修改

- 从 `runs/art_styles_c24_graphic_v6/student.pt` 重新开始，新增 `algo/train_art_styles_v15.py`。方向梯度、区域笔触连续性、浮世绘块内平坦和边界、墨色分区、相机扰动和移位一致性全部只在训练监督中使用。
- v15 全量训练 3,000 步，输出 `runs/art_styles_c24_v15_v6_restart_full/student.pt`。
- 同一起点完成单因素消融：梵高方向项×4、浮世绘平坦项×5、水墨低色度项×5。浮世绘平坦项×5 进入下一阶段，输出 `runs/art_styles_c24_v15_ablate_ukiyoflat5_ramp/student.pt`。
- 用 100 张训练集图重新生成候选专用整数合同，文件为 `audits/v15_v6_restart_20261005/qparams_flat5_styleqat_100.json/.npz`；训练与评估留出图不重叠。
- 用固定合同进行 900 步整数 QAT，输出最终候选 `runs/art_styles_c24_v15_flat5_qat900_calibrated/student.pt`，并再次从该 checkpoint 导出最终 qparams。

## 200 张留出图结果（FP32，v6 对照）

结果文件：`audits/v15_v6_restart_20261005/styleqat_fp32_metrics_200/summary.json`。

| 风格 | edge-F1 | 关键结构统计 | v6 对照 |
|---|---:|---|---|
| 梵高 | 0.927 | surface detail 0.0334 | v6 edge-F1 0.845 | 
| 浮世绘 | 0.931 | flat interior 0.345、boundary gradient 0.1019 | v6 0.907、0.412、0.0957 |
| 水墨 | 0.924 | background paper 0.740、subject dark 0.382 | v6 0.922、0.688、0.397 |

这些统计与匿名 A/B 盲评表一起使用，不能单独替代人眼风格判断。盲评表已生成 48 张：`audits/v15_v6_restart_20261005/blind_pair_16/`。

## 24 张整数对拍结果

结果文件：`audits/v15_v6_restart_20261005/flat5_qat_style_ownq_paired24/summary.json`。整数输出使用候选自身导出的 qparams，避免把初始 checkpoint 的权重误当成最终候选。

| 风格 | 整数相对 FP32 艺术参考 PSNR | SSIM | edge-F1 |
|---|---:|---:|---:|
| 梵高 | 25.17 dB | 0.876 | 0.901 |
| 浮世绘 | 27.26 dB | 0.875 | 0.883 |
| 水墨 | 25.63 dB | 0.873 | 0.862 |

相同协议下，整数相对自身 FP32 的 PSNR/SSIM 分别为 21.42/0.818、24.08/0.817、21.43/0.812。PSNR/SSIM 的参考对象、图像数、分辨率和量化状态必须随结果一起报告。

## 视频代理测试

- FP32 CUDA 30 帧回放：`audits/v15_v6_restart_20261005/camera30_final_styleqat/summary.json`。输入来自真实 USB 相机保存的 30 帧 640×480 序列；风格切换和相邻帧一致性均已计算，未声称 FPGA FPS。
- 整数 golden 30 帧回放：`audits/v15_v6_restart_20261005/integer_camera30_styleqat/summary.json`。三个风格的对齐 MAE 分别为 13.96、7.48、6.71（0–255），CPU golden 中位单帧约 201 ms，仅用于时序和数值回放，不能作为 FPGA 性能。

## 合法参考图与边界

参考图的 SHA256、来源 URL 和角色记录在 `runs/art_styles_c24_v15_ablate_ukiyoflat5_ramp/references.json`、`dataset_v2/manifests/met_candidates*.jsonl` 和 `dataset_v2/manifests/aic_v9.json`。The Met 的公开域图像按其 Open Access/CC0 政策可自由使用，来源记录见 [The Met Open Access](https://www.metmuseum.org/hubs/open-access)。

## 尚未通过的项目

- `board_validated=false`：尚未在 Ti60F225I3 + SC431HAI 上完成 CSI-2、DDR ping-pong、HDMI、稳定帧率、动态切换延迟和唯一 `frame_id` 验收。
- 尚未把 qparams 写入最终 RTL/Efinity 镜像，也没有声称板端综合或实测资源已完成。
- 最终候选可进入下一步 PC 整数/RTL 逐层对拍；若板端整数风格退化，应回到候选自身 qparams 和 QAT 合同复查，不能只看 FP32 预览。
