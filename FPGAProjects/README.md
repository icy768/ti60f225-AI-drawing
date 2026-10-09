# FPGA 工程统一入口

最新交接：[项目交接文档（2026-10-09）](docs/项目交接文档_20261009.md)，适用RISC-V 08；包含操作、参数、构建和清理记录。

唯一开发目录为本仓库 `FPGAProjects`；Git 根目录是上一级 FPGA。当前 `feat/basic-requirements` 分支已验收 **RISC-V 08 / V21b**，ID `53430a08`，已固化并验证 RESET_N 后的自主启动。

| 目录 | 用途 | 工程入口 |
|---|---|---|
| [StyleCam_camera](StyleCam_camera/README.md) | 当前完整 RISC-V / 摄像头 / 三风格网络 / DDR / HDMI 整机 | `StyleCam_camera/ti60f225_oob.xml` |
| [StyleCam](StyleCam/README.md) | V21b 训练、量化与成套导出 | `StyleCam/syn/vision_map.xml` |
| [sc431hai_hdmi](sc431hai_hdmi/README.md) | 未修改的独立摄像头参考 | `sc431hai_hdmi/ti60f225_oob.xml` |
| [烧录文件](烧录文件/README.md) | 当前 08 包与历史恢复包 | BIT 临时下载，HEX 固化 |
| tools | 本机共用 Icarus Verilog | `tools/iverilog/mingw64/bin` |

## 当前版本与操作

[08 发布包](烧录文件/20261009_RISCV08_BGGR_RGBMirror/README.md) 包含 BIT/HEX、75 个匹配源码哈希、资源/时序报告和固化验收。Flash 地址 0，1,073,814 字节独立回读一致；模型位于 `0x200000`，48,616 字节保持一致，启动 CRC `373deed7`。用户已确认画面正常。

摄像头恢复原生 BGGR、原初始化与颜色配置；水平翻转移至 RGB 写 DDR。曝光/增益与原例程相同。640×480 输出和用户确认的 CSI FIFO=1024 保留；完整 FIFO=4096 会使集成工程 RAM 超限。

在 `StyleCam_camera` 执行 `.\program_ram.ps1 -UartPort COM19` 临时下载，`python -B program_flash_native.py` 固化，`.\verify_flash_boot.ps1 -UartPort COM19` 监听复位启动。工具路径可通过参数指定。固化前先执行 `python -B program_flash_native.py --check-only`。

KEY3 切换风格；KEY2 / 串口 `v` 轮换布局；串口 `c` 回读摄像头，`s` 查状态。复位默认对比布局。RISC-V 从 Flash 加载权重并部署三种风格，约 15 FPS；摄像头约 29.9 FPS。自主启动验收错误计数为 0。

当前资源 XLR 60399/60800、RAM10 246/256、DSP 121/160，setup +0.395 ns、hold +0.026 ns。摄像头全尺寸 3 帧、921600 个 RGB 像素逐值一致；RGB 翻转 DDR 地址和像素顺序、采集/调度/显示/APB 回归通过。

## 记录

- [摄像头修复与原因判断](docs/原生BGGR与RGB翻转验证_20261009.md)
- [参考对齐与 FIFO 资源冲突](docs/摄像头参考对齐与资源冲突_20261009.md)
- [工程整理与验收索引](docs/工程整理与验收.md)
- [10 月 6 日历史交接文档](docs/项目交接文档_20261006.md)：当时为全 RTL SCU09，操作和资源数据以当前整机 README 为准。

桌面另一个 `ti60f225-AI-drawing/FPGAProjects` 保留作用户删除前的参考；当前工程在本路径开发，原摄像头例程未改动。
