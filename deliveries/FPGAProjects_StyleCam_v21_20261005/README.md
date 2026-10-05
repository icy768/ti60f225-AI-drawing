# StyleCam v21 硬件交付

本目录是从 `develop` 生成的 StyleCam v21b 交付快照。它保留 v6 已有的摄像头、DDR、HDMI、SoC 和 FPGA 视觉子系统文件，并加入 v21b 训练、INT8 部署文件和复验记录。

- [总交付说明](交付说明.md)
- [硬件组接入说明](StyleCam/docs/v21_hardware_handoff_20261005.md)
- [v21 优化与指标报告](StyleCam/docs/v21_targeted_optimization_20261005.md)
- [v21 计划复核](StyleCam/docs/fns_experience_to_v21_review_20261005.md)
- [机器可读部署状态](deployment_status.json)
- [文件 SHA256 清单](sha256_manifest.json)

硬件组直接取用：

- `StyleCam/rtl/gen/v21b_ukiyoe_qat900_640x480/`
- `StyleCam/sw/net_blob.h`
- `StyleCam/sw/in_params.h`
- `StyleCam/audits/v21b_pc_validation_ncal16/art_styles_c24_v21b_ukiyoe_qat900_soft15/validation.json`

本包不包含 Python 虚拟环境、完整 COCO/训练数据集、Efinity 安装包，也不把原厂摄像头演示 bitstream 误标为 v21 网络 bitstream。板级 bitstream、匹配 ELF、真实 SC431HAI 视频和持续帧率仍需硬件组完成。
