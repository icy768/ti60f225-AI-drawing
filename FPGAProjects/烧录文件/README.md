# 烧录文件

当前版本：[RISCV10 / 低延迟与连续帧优化](20261015_RISCV10_LowLatency_Candidate/README.md)，ID `53430a0a`。已 RAM 下载；40 秒实机采样 29.99～30fps、零新增跳帧，三次 UART 风格切换最大 52.534ms。最终时序与八组离线回归通过，资源 XLR58284、RAM245、DSP145。

**用户要求跳过本次 Flash 固化，RISCV10 尚未验收掉电启动。** 当前已固化的历史恢复基线：[RISCV08 / 原生 BGGR 与 RGB 水平翻转](20261009_RISCV08_BGGR_RGBMirror/README.md)，ID `53430a08`。

六个 RISCV09 调试包已清理，恢复归档仅保留在本地 `_archive/20261015_RISCV09_debug_packages.zip`，不上传仓库。保留 Resource2 的精简资源与时序比较数据。详见 [资源复核与 30fps 来源](../docs/资源复核与30fps来源_20261015.md) 和 [清理记录](../docs/调试包清理_20261015.json)。

更早恢复资料：

- [RISCV04 水平镜像](20261008_RISCV_HMirror/README.md)
- [SCU09 V21b 全 RTL](20261006_SCU09_V21b_摄像头版/README.md)
- [SCU08 摄像头修复](20261006_SCU08_V6_摄像头修复版/README.md)
