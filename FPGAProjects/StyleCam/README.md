# StyleCam V21b 三风格网络

本目录保存实时 AI 绘画项目的模型训练、量化、导出、整数参考和历史评估。完整实机工程位于相邻的 [StyleCam_camera](../StyleCam_camera/README.md)，摄像头统一为 **SC431HAI**。项目最新分支、板测范围和剩余事项见[根 README](../../README.md)。

## 当前模型

- 版本：V21b / QAT900，三风格为 Van Gogh、Ukiyo-e、Ink Wash。
- 实际输入输出：640×480；固定 C24/Fc16、13 层网络。
- 参数量：11,028；部署 blob：48,616 字节；VGA 卷积计算量约 339,148,800 MAC/帧。
- FPGA 实现卷积、ReLU、定点 IN 及更新；完整整机由 Sapphire RISC-V 负责初始化、参数装载和任务调度。

RISCV10 提高推理时钟与末层并行度，保持原有模型、权重和 INT8 精度。板端约 30fps 的证据属于 RISCV10 整机的短时采样，不是本目录独立训练脚本或算法子系统的帧率。

## 使用入口

整机部署以 StyleCam_camera 内配套的 RTL、model/net_blob.bin、固件和 ROM 为准，Efinity 入口是该目录的 ti60f225_oob.xml。不要把本目录的算法子系统工程直接当作完整摄像头位流。

算法导出中的 `rtl/gen/v21b_ukiyoe_qat900_640x480/`、`sw/net_blob.h`、`sw/in_params.h` 必须成套使用；`syn/vision_map.xml` 用于子系统验证。早期独立 BSP / vision_top 的板级配置和输入模式说明仅适用于该次交付，不能覆盖当前 SC431HAI 1080p RAW10 → VGA 整机配置。

训练和量化更新须同时保留 checkpoint、qparams、导出 RTL/mem/blob、IN 参数以及数值验证记录，不能只替换某一个权重文件。

## 验证口径

audits 和交付文档记录各自版本的 PC 与历史验收范围，不是清理后重新执行的实机结果。RTL 与整数参考逐像素一致证明算术实现一致；画质、视频稳定性与板端性能需要分别验证。

现有 24 图 PSNR/SSIM 评估的参考是指定 FP32 艺术教师，不能表述为原照片重建分数、标准 CycleGAN 对比或官方评分。动态 IN 和摄像头输入会影响实际显示效果；正式提交材料仍需同协议标准网络对比、结构图和实板视频。

历史接入说明见 docs/v21_hardware_handoff_20261005.md；当前状态以[项目进度](../docs/赛题指标与完成情况_20261015.md)为准。
