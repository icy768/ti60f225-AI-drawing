# FPGA 工程与交付入口

本项目使用 **Ti60F225 + SC431HAI** 实现三风格 AI 绘画。所有本地文件统一在 `C:\Users\lingye\Desktop\FPGA`，当前路径与状态见 [工程入口](../工程入口.md)。

| 目录 | 用途 |
|---|---|
| [StyleCam_camera](StyleCam_camera/README.md) | 完整摄像头 / DDR / CNN / RISC-V / HDMI 工程，唯一整机入口 `ti60f225_oob.xml` |
| [StyleCam](StyleCam/README.md) | V21b 网络训练、量化、导出、整数参考及历史交付证据 |
| [sc431hai_hdmi](sc431hai_hdmi/README.md) | 独立摄像头和 HDMI 参考，不替代完整整机 |
| [烧录文件](烧录文件/README.md) | 分版本下载与恢复包；实际包含哪些包取决于分支 |
| [docs](docs/赛题指标与完成情况_20261015.md) | 当前状态、性能边界、资源与历史交接记录 |
| [新版 D1B60/FWP1](StyleCam_camera/experiments/v21b_fwp1_20261023/README.md) | 10月22日新网络，离线复测完成，未上板 |
| [reference](reference/README.md) | 常用板卡/摄像头 PDF、ISP 原例程、VC02 指南 |
| `_archive/` | 必要历史恢复资料与厂家源码压缩归档 |
| [tools](tools/README.md) | Icarus、ESP32、VC02 本地工具，安装下载缓存已清理 |

正式基线为 RISCV11 AE/IN4；现有新版、V5 和语音扩展保留各自状态。真实 720p30 神经网络推理尚未完成。

当前本地整理分支为 `codex/consolidated-project-20261023`；原分支和已有本地修改均保留。按用户安排，只检测板卡连接，暂不下载/烧录；本次目录整理没有改变板上配置，也未提交或推送 GitHub。
