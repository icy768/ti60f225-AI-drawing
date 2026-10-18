# 下载包与恢复资料

**当前默认正式版为 [RISCV11 AE / IN4，2026-10-18](20261018_RISCV11_Main_AE_IN4_Release/README.md)。** 总工程入口为 `FPGAProjects/StyleCam_camera/ti60f225_oob.xml`，摄像头为 SC431HAI。

| 版本 | 用途与验收 |
|---|---|
| [RISCV11 AE / IN4 正式版](20261018_RISCV11_Main_AE_IN4_Release/README.md)，ID `53430a0b` | 自动曝光和三风格用户确认；短时约 30fps、Flash 独立回读及 RESET_N 自主启动通过 |
| RISCV11 R1 / R2 / R3 / R4 候选 | 保留各轮资源对照、回归摘要与原始构建证据；默认下载已改为正式版 |
| [RISCV10 基线](https://github.com/icy768/ti60f225-AI-drawing/blob/codex/resource-throughput-20261013/FPGAProjects/烧录文件/20261015_RISCV10_LowLatency_Candidate/README.md)，ID `53430a0a` | 历史 40 秒 VGA 约 30fps；Flash 独立回读与配置复位启动通过，保留恢复分支 |
| [RISCV08 恢复包](https://github.com/icy768/ti60f225-AI-drawing/blob/feat/basic-requirements/FPGAProjects/烧录文件/20261009_RISCV08_BGGR_RGBMirror/README.md)，ID `53430a08` | 保留早期自主启动恢复基线 |

当前 `program_ram.ps1`、`program_flash_release.py` 默认正式版；RISCV10 入口增加 `riscv10` 后缀以免误下旧包。正式版 BIT / HEX、固件、模型、源码哈希和验证记录须成套使用；多个 RISCV11 包的 ID 相同，应以目录及 SHA256 区分。

本次 Flash 验收使用实体 RESET_N，物理断电重启和长期压力测试待补验。手机预览及 AWB 默认关闭，新网络和手势未接入。完整记录见[固化与集成说明](../docs/RISCV11固化与总工程集成_20261018.md)。
