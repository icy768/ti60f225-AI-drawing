# StyleCam 摄像头整机 — 资源与吞吐优化

开发分支 `codex/resource-throughput-20261013`，源码 ID `53430a0a`（RISCV10 低延迟）；完整固化验收的历史基线为 RISC-V 08 / `53430a08` / `77e5838`。唯一工程入口为本目录 `ti60f225_oob.xml`。

当前源码进行 [低延迟与连续帧优化](../docs/低延迟与帧调度优化_20261015.md)：推理域 150MHz、控制域 100MHz、末层 PE12、四个外部 DDR 输入银行，保持原模型和 HDMI 输出。最终时序与八组离线回归均已通过；[RISCV10 下载包](../烧录文件/20261015_RISCV10_LowLatency_Candidate/README.md) 已生成，由用户手动下载。完整 VGA 仿真 30.45ms，下载后 40 秒实机采样为 29.99～30fps、零新增跳帧、三次 UART 风格切换最大 52.534ms；长时稳定性及其他布局待验证。

资源复核及吞吐解释见 [资源复核与 30fps 来源](../docs/资源复核与30fps来源_20261015.md)。此前 Resource2 调试包已清理，精简比较数据保存在 `validation/resource2/manifest.json`。RISCV10 已由用户 RAM 下载；本次用户要求跳过 Flash 固化，尚未验收掉电启动。

**接手先读 [项目交接文档（2026-10-09）](../docs/项目交接文档_20261009.md)**：按键/串口、OSD含义、摄像头参数、烧录/构建、验收证据与剩余事项均在其中。

## 已验收 08 基线

SC431HAI → 原生BGGR 5×5 MHC与原Gamma → 中央裁剪/2×2平均 → 640×480 RGB水平翻转写DDR三缓冲 → V21b 13层网络与板内IN → HDMI 1080p60。RISC-V负责初始化、权重加载、调度、中断与UART。

用户确认08画面正常。Flash地址0的1,073,814字节独立回读一致，RESET_N后的自主启动通过，模型CRC `373deed7`，ready=7。最新启动运行FPS=14.99、CAM=29.9，错误计数为0。曝光00/46/00、模拟增益83/20、数字增益00/80、RGB256/256/256，传感器镜像00；翻转在RGB阶段完成。CSI FIFO=1024，无AE/AWB。

[当前发布包](../烧录文件/20261009_RISCV08_BGGR_RGBMirror/README.md) 保存BIT/HEX、文件哈希、匹配源码和固化证据。资源XLR60399/60800、RAM10 246/256、DSP121/160，setup +0.395ns、hold +0.026ns。

## 操作

**K0 切布局**（分屏→风格全屏→原画全屏）；KEY3 短按切三种风格，长按约0.7秒仍可切布局。UART `0/1/2`选风格、`v`切布局、`s`状态。默认COM19，115200 8N1。`k0`计数表示K0事件，`k3`包括KEY3短按和长按。底部KEY3提示已清空。

```powershell
# 核对当前 RISCV10 发布包；不访问硬件
.\program_ram.ps1 -CheckOnly
# RAM 临时下载，指定实际串口
.\program_ram.ps1 -UartPort COM19
# 未来连接开发板后再执行 Flash 写入；本次未执行
python -X utf8 program_flash_release.py --check-only
python -X utf8 program_flash_release.py
# 写入并独立回读成功后，按 RESET_N 或重新上电验收
.\verify_release_flash_boot.ps1 -UartPort COM19
```

当前默认 RAM 入口已切到 RISCV10，旧 `program_native_ram.ps1` 与 `program_flash_native.py` 仅供 RISCV08 历史恢复。固化工具会先核对位流、已构建源码、时序和实机证据，再备份配置区域并校验模型；Flash 写后执行独立逐字节回读。RISCV10 本轮按用户要求未固化。

## 记录

- [原生BGGR、RGB翻转与原因判断](../docs/原生BGGR与RGB翻转验证_20261009.md)
- [摄像头参考对齐与FIFO资源冲突](../docs/摄像头参考对齐与资源冲突_20261009.md)
- [文件清理记录](../docs/文件清理记录_20261009.md)
- [固化烧录与历史04复核](../docs/固化烧录与恢复复核_20261008.md)

04、SCU09和SCU08包作为历史恢复资料；历史08交接文档只适用于旧版，当前操作以本文为准。临时构建和调试材料的处理见清理记录。
