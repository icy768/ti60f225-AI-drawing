# FPGA 工程入口

当前完整工程：[StyleCam_camera](StyleCam_camera/README.md)，Efinity 工程 `ti60f225_oob.xml`。当前 RISCV10 / `53430a0a`，推理 150MHz、控制 100MHz，640×480 实际处理，HDMI 1080p60。

用户 RAM 下载后的 40 秒实测：29.99～30fps、零新增跳帧、三次 UART 风格切换最大 52.534ms。用户要求暂时跳过 Flash 固化；已固化恢复基线仍为 RISCV08。

- [当前烧录包与验收](烧录文件/20261015_RISCV10_LowLatency_Candidate/README.md)
- [资源复核与 30fps 来源](docs/资源复核与30fps来源_20261015.md)
- [低延迟实现](docs/低延迟与帧调度优化_20261015.md)
- [训练、量化、导出](StyleCam/README.md)
- [未修改的独立摄像头参考](sc431hai_hdmi/README.md)
- [历史 RISCV08 恢复包](烧录文件/20261009_RISCV08_BGGR_RGBMirror/README.md)

K0 切布局；KEY3 短按切风格、长按约 0.7 秒切布局。UART 默认 COM19、115200 8N1，`0/1/2/v/s/c`。当前 XLR58284/60800、RAM10 245/256、DSP145/160，setup +0.278ns、hold +0.026ns。

六个 RISCV09 调试包已从发布目录清理，本地校验归档留在 `_archive`；精简比较数据保留，详见 [清理记录](docs/调试包清理_20261015.json)。
