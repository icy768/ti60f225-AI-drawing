# FPGA 工程与交付入口

本项目使用 **Ti60F225 + SC431HAI** 实现实时三风格 AI 绘画。项目总体介绍见[根 README](../README.md)，最新证据与缺口见[当前进度](docs/赛题指标与完成情况_20261015.md)。

| 目录 | 用途 |
|---|---|
| [StyleCam_camera](StyleCam_camera/README.md) | 完整摄像头 / DDR / CNN / RISC-V / HDMI 工程，唯一整机入口 `ti60f225_oob.xml` |
| [StyleCam](StyleCam/README.md) | V21b 网络训练、量化、导出、整数参考及历史交付证据 |
| [sc431hai_hdmi](sc431hai_hdmi/README.md) | 独立摄像头和 HDMI 参考，不替代完整整机 |
| [烧录文件](烧录文件/README.md) | 分版本下载与恢复包；实际包含哪些包取决于分支 |
| [docs](docs/赛题指标与完成情况_20261015.md) | 当前状态、性能边界、资源与历史交接记录 |

RISCV10 在 40 秒实机窗口内达到 VGA 29.99～30fps、无新增跳帧；HDMI 为 1080p60 显示扫描。2026-10-16 完成 Flash 固化、1075167 字节独立回读及配置复位自主启动验收；模型保持不变。语音 / 手机预览候选已通过代码和离线验证，尚未上板。真实 720p30 神经网络推理尚未完成。

当前 **不合并、不删分支**，先完成实机验证。main/develop 仍为既有 SCU09 功能源码；RISCV08 恢复基线、RISCV10 和交互候选分别位于 feat/basic-requirements、codex/resource-throughput-20261013、fw/creative-interaction。不要把项目进度说明当作默认分支已包含全部功能的声明。
