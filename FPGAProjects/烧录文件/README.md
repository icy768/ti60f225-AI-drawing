# 下载包与恢复资料

**当前默认正式版为 [RISCV11 AE / IN4 + 手机预览，2026-10-30](20261030_RISCV11_PhonePreview_Release/README.md)。** 总工程入口为 `FPGAProjects/StyleCam_camera/ti60f225_oob.xml`，摄像头为 SC431HAI。

| 版本 | 用途与验收 |
|---|---|
| [RISCV11 AE / IN4 + 手机预览正式版](20261030_RISCV11_PhonePreview_Release/README.md)，ID `53430a0b` | 三风格 30fps、手机 160×120 风格画约 15 帧/s；Flash 独立回读及 RESET_N 自主启动通过；控制口改到 J28-37 |
| [RISCV11 AE / IN4（10-18）](20261018_RISCV11_Main_AE_IN4_Release/README.md)，ID `53430a0b` | 不带预览的上一正式版；电脑 FTDI 串口可控制；`program_flash_release.py --release <该目录>` 可恢复 |
| ESP32 / VC02 交互包（10-20 ～ 10-21） | 三板语音 / Wi-Fi 接入准备与联调资料 |

2026-10-30 已删除 10-18 以前的旧包（SCU08/SCU09、HMirror、RISCV08、RISCV10、RISCV11 R1～R4 候选）及对应恢复分支和标签。

当前 `program_ram.ps1`、`program_flash_release.py` 默认正式版。正式版 BIT / HEX、固件、模型、源码哈希和验证记录须成套使用。

Flash 验收使用实体 RESET_N，物理断电重启和长期压力测试待补验。AWB 默认关闭，新网络和手势未接入。10-18 版记录见[固化与集成说明](../docs/RISCV11固化与总工程集成_20261018.md)。
