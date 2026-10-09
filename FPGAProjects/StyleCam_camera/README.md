# StyleCam 摄像头整机 — RISC-V 08

当前分支 `feat/basic-requirements`，ID `53430a08`，完整源码基线 `77e5838`。唯一工程入口为本目录 `ti60f225_oob.xml`。

**接手先读 [项目交接文档（2026-10-09）](../docs/项目交接文档_20261009.md)**：按键/串口、OSD含义、摄像头参数、烧录/构建、验收证据与剩余事项均在其中。

## 当前状态

SC431HAI → 原生BGGR 5×5 MHC与原Gamma → 中央裁剪/2×2平均 → 640×480 RGB水平翻转写DDR三缓冲 → V21b 13层网络与板内IN → HDMI 1080p60。RISC-V负责初始化、权重加载、调度、中断与UART。

用户确认08画面正常。Flash地址0的1,073,814字节独立回读一致，RESET_N后的自主启动通过，模型CRC `373deed7`，ready=7。最新启动运行FPS=14.99、CAM=29.9，错误计数为0。曝光00/46/00、模拟增益83/20、数字增益00/80、RGB256/256/256，传感器镜像00；翻转在RGB阶段完成。CSI FIFO=1024，无AE/AWB。

[当前发布包](../烧录文件/20261009_RISCV08_BGGR_RGBMirror/README.md) 保存BIT/HEX、文件哈希、匹配源码和固化证据。资源XLR60399/60800、RAM10 246/256、DSP121/160，setup +0.395ns、hold +0.026ns。

## 操作

KEY3切换三种风格；KEY2/串口`v`轮换对比→风格全屏→原画全屏；串口`0/1/2`选风格、`s`状态、`c`摄像头回读、`g?`回车查询RGB。默认COM19，115200 8N1。最新日志未覆盖物理KEY2动作，接手检查见交接文档。

```powershell
.\program_ram.ps1 -UartPort COM19
python -X utf8 -B program_flash_native.py --check-only
python -X utf8 -B program_flash_native.py
# 监听期间按RESET_N或重新上电
.\verify_flash_boot.ps1 -UartPort COM19
```

默认脚本使用已验收08，缺少本地outflow时读取正式发布包。修改源码或镜像后必须重新验收；旧SCU09主机工具不适用于08。

## 记录

- [原生BGGR、RGB翻转与原因判断](../docs/原生BGGR与RGB翻转验证_20261009.md)
- [摄像头参考对齐与FIFO资源冲突](../docs/摄像头参考对齐与资源冲突_20261009.md)
- [文件清理记录](../docs/文件清理记录_20261009.md)
- [固化烧录与历史04复核](../docs/固化烧录与恢复复核_20261008.md)

04、SCU09和SCU08包作为历史恢复资料；当前操作以08交接文档为准。临时构建和调试材料的处理见清理记录。
