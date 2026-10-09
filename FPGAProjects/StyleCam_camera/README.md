# StyleCam 摄像头整机 — RISC-V 版（分支 feat/basic-requirements）

## 当前 08 版：原生 BGGR，RGB 水平翻转（2026-10-09）

已恢复摄像头例程的原生方向、191 条初始化命令与 BGGR 插值，传感器镜像回读 `3221=00`。左右翻转移至 RGB 写入 DDR 时完成，原画与风格输入方向保持一致。曝光 `00/46/00`、模拟增益 `83/20`、数字增益 `00/80`、RGB `256/256/256`、黑电平与原 Gamma 保持原配置。FIFO=1024。

源码、运行与固化 ID `53430a08`；全尺寸 921600 个 RGB 像素及 DDR 翻转地址／像素顺序检查通过，三缓冲与控制回归通过。资源 XLR 60399/60800, RAM10 246/256, DSP 121/160；setup +0.395 ns、hold +0.026 ns。实板启动、寄存器和运行计数验收通过；用户已确认“这回正常了”。Flash 复位启动默认左原画/右风格，KEY2 或串口 `v` 轮换布局。

已固化 Flash 地址 0，1,073,814 字节独立回读完全一致，模型 48,616 字节保持一致。用户复位后已捕获完整自主启动，模型 CRC `373deed7`，三风格 ready=7，FPS=14.99、CAM=29.9，采集/视频/欠流/HDMI/中断错误为 0。

发布包：[RISC-V 08 / BGGR / RGB 翻转](../烧录文件/20261009_RISCV08_BGGR_RGBMirror/README.md)。当前默认工具：临时加载 `.\program_ram.ps1 -UartPort COM19`；固化 `python -B program_flash_native.py`；固化后复位验收 `.\verify_flash_boot.ps1 -UartPort COM19`。源码或位流哈希变化会拒绝用旧验收记录固化。详细证据和本机回退备份见 [原生 BGGR 与 RGB 翻转记录](../docs/原生BGGR与RGB翻转验证_20261009.md)。

恢复原生 BGGR、将翻转移到 RGB 后画面恢复，RAW 相位适配是主要嫌疑；同一位流第二次加载才获得正常反馈，无法排除加载/显示状态的影响。未增加自动曝光或自动白平衡。

## 历史 07 版：原摄像头参考对齐（2026-10-09）

历史 07 版源码 ID `53430a07`，已通过 JTAG 临时加载与串口验收。参考工程为 `C:\Users\lingye\Desktop\ti60f225-AI-drawing\FPGAProjects\sc431hai_hdmi`；保留 RISC-V 初始化方式、水平镜像与 640×480 画面尺寸。

黑电平 16、完整四相位 5×5 MHC、原 Gamma、16 位 Q8.8 增益与零值回退对齐原例程；R/G/B 默认为 `256/256/256`（100%）。HDMI VIC 改回原值 0。曝光 `00/46/00`、模拟增益 `83/20` 保持原值。

FIFO=4096 的实测资源为 271/256 RAM，无法装入；经用户确认保留 1024。CPU 控制和网络 RGB 输入架构保留，具体冲突与适配见 [对齐记录](../docs/摄像头参考对齐与资源冲突_20261009.md)。

串口：`g R G B` + 回车设整数百分比 0～25599；`q R G B` + 回车设原始 Q8.8 值 0～65535；`g?` / `q?` 查询；`G` 恢复 100%。值 0 按原例程解释为有效 255/256（约 99.6%）。

完整输入仿真 921600 个 RGB 像素一致，整机回归通过。XLR 60430/60800，RAM 246/256，DSP 121/160；setup +0.367 ns、hold +0.026 ns。串口回读 ID `53430a07`，三通道最终为 `256/256/256`，曝光/增益保持原例程数值。FPS 约 15、CAM 约 30，各链路错误计数为 0。

本版位流 `outflow_original_align/ti60f225_oob.bit`；校验记录 `validation/camera_original_align.json`；临时加载 `.\program_original_ram.ps1 -UartPort COM19`。本次未改 Flash；断电后仍启动 `53430a04`。物理画质需观察确认。历史 06 和 05 位流保留在 `outflow_rgb_gain` 和 `outflow_mhc`。

复验：`python -B sim_camera.py`；完整尺寸：`python -B sim_camera_mhc.py --full`。

## 历史 04 固化版本与工程入口（2026-10-08）

唯一工程入口为 `C:\Users\lingye\Desktop\FPGA\FPGAProjects\StyleCam_camera\ti60f225_oob.xml`；Git 根目录为 `C:\Users\lingye\Desktop\FPGA`，分支 `feat/basic-requirements`。

2026-10-08 当时的固化 ID `53430a04`：SC431HAI 水平翻转 `3221=06`，配套 GBRG 相位；曝光 `00/46/00`（1120 半行）、模拟增益 `83/20`（6.16 倍）、数字增益 `00/80`（1 倍）、三个通道使用原 Gamma。与原 RISC-V 版本逐条对比，摄像头表仅增加镜像写入和读校验，共 193 条。

启动先通过 `0xAB` 唤醒配置 Flash，再从 `0x200000` 加载权重，修复配置后 Flash 休眠导致固化启动无法读取权重的问题。串口新增只读命令 `c`，回读实际曝光、增益和镜像寄存器。

固化状态：**已复位，从 Flash 自主启动验收通过**。配置区 1050510 字节已逐字节独立回读，模型权重 48616 字节保持一致。备份和日志见 `validation/camera_mirror_flash.json`；详细记录见 `../docs/固化烧录与恢复复核_20261008.md`。

本机 UART 为 COM19、115200 8N1。04 版操作工具保存在历史 Git 提交 `fc36933`；当前默认脚本执行上方 08 版。固化脚本要求镜像已经过 JTAG 启动验收，先备份，后写入和独立回读，并核对权重区。

固件构建：`cmd /c embedded_sw\soc\software\standalone\stylecam\build_fw.bat`。可通过 `STYLECAM_PYTHON`、`STYLECAM_RISCV_BIN`、`STYLECAM_EFINITY`、`STYLECAM_BUILD_DIR` 指定 Python、编译器、Efinity 和 ASCII 构建目录。目录整合记录见 `../docs/目录统一与水平镜像_20261008.md`。

在已验收的 V21b / SCU09 全 RTL 整机上补齐赛题一基础要求：加入 Sapphire RISC-V，C 驱动负责摄像头初始化、权重加载、加速器调度与中断；HDMI 增加原画/风格画对比和 OSD 帧率叠加。
网络、预处理、DDR 与 HDMI 时序沿用 V21b；整网逐位仿真（9 帧、6912 像素、936 个 IN 系数）在新结构下仍全部一致。

| 基础要求 | 实现 | 板测（r4，2026-10-07） |
|---|---|---|
| CSI-2 采集、RAW→RGB、640×480@30、DDR 乒乓 | SC431HAI 4 lane；输入改三缓冲，正在显示的原画所在缓冲不被覆盖 | 传感器 30.0 fps，采集错误 0 |
| 卷积/ReLU/IN 硬件化，AXI 读写 DDR | V21b 13 层网络 + 板内 IN | 每帧 54–60 ms |
| HDMI 输出 | 1080p60 | 欠流 0 |
| RISC-V 摄像头初始化 | `camera_init()`：上电时序 + 191 条寄存器（写/读校验/延时/诊断读），经 APB I2C 命令口 | 191 条全部通过，3e01=0x46、320e/f=05/dc |
| RISC-V 权重加载与部署 | 位流不含权重；`weights_load()` 经 SPI0 从配置 Flash 0x200000 读 `model/net_blob.bin`，CRC32 校验后写入 4050 条权重/系数；开机依次部署三种风格（IN 校准 13 遍） | 212 ms 装载完成；运行中串口 `w` 可热重载 |
| RISC-V 任务调度（启动、等待、中断） | 每帧 CPU 下发单步启动；帧发布中断（PLIC 用户中断 A）里统计并启动下一帧 | 15.0 fps，中断错误 0 |
| 原画 vs 风格画 | KEY2 / 串口 `v` 轮换：左原画｜右风格画（各 1.5 倍）→ 风格画全屏 → 原画全屏；左侧原画就是生成右侧那帧的同一输入帧 | 三种布局欠流 0 |
| 屏幕 FPS ≥15 | OSD：FPS、风格名、单帧耗时、传感器帧率、操作提示 | 15.0（锁定 60 Hz/4） |

## 链路

SC431HAI RAW10 → 黑电平 / RGB 增益 / 四相位原生 BGGR 5×5 插值 / 逐像素 Gamma / 中央裁剪与 2×2 RGB 平均缩小 → RGB 水平翻转写入 640×480 三缓冲 → V21b 13 层网络与板内 IN → 输出双缓冲 → HDMI 1080p60（布局 + OSD）。
Sapphire（RV32I，16 KB 片上 RAM，100 MHz）：UART0 控制台、SPI0 读配置 Flash、APB3 从口 0（0xF8100000，`rtl/sc_apb_regs.v`）、用户中断 A。

## 上电与操作

1. Flash 0x200000 需有权重包（一次性）：`python flash_blob.py --efinity <Efinity 目录>`（只擦写该处 48 KB，位流区不动，回读比对）。
2. 下载位流后自动运行：装载权重 → 配置传感器（含 5 s 稳定）→ 部署三种风格 → 实时运行，约 8 s。
3. KEY3 / 串口 `0` `1` `2`：风格；KEY2 / 串口 `v`：布局；串口 `s` 状态，`c` 只读摄像头寄存器，`w` 重载权重；`g R G B` + 回车调通道，`g?` + 回车查询，`G` 恢复 100%。串口 COM19（FT4232 C 口），115200 8N1。

## 编译、下载、验收

```powershell
# 固件（生成传感器表、权重包校验头，编译，写入 ip\soc 与 fw_rom）
cmd /c embedded_sw\soc\software\standalone\stylecam\build_fw.bat
# 整机（STYLECAM_EFINITY 指向 Efinity 安装目录；STYLECAM_BUILD_DIR 为 ASCII 构建目录）
$env:STYLECAM_EFINITY='D:/yilinsiFPGA/efinity/2026.1'; $env:STYLECAM_BUILD_DIR='D:\yilinsiFPGA\build\stylecam'
python -B build.py interface; python -B build.py map; python -B build.py pnr; python -B build.py pgm
# 只改固件：不重新综合布线，约 10 s 出新位流（<构建目录>\outflow_fw）
python -B fw_update.py D:\yilinsiFPGA\build\stylecam --efinity D:/yilinsiFPGA/efinity/2026.1
# 串口验收（启动日志、帧率、错误计数、切换延迟）
python -B cpu_monitor.py --port COM19 --boot 25 --seconds 60 --switch
```

仿真（`$env:ICARUS_BIN` 指向 Icarus bin）：`sim_camera.py`（采集三缓冲、调度、显示、APB 寄存器）、`sim_display_pressure.py`（三种布局 90 拍 DDR 延迟下逐像素、无欠流；并复现旧版欠流）、`sim_osd.py`（OSD 逐像素）、`sim_video_engine.py`（权重 RAM 无初值，经 CPU 写口装载全部 4050 条后 9 帧逐位对拍，需 PyTorch 环境，`PYTHONUTF8=1`）。

历史资源（r4，摄像头本次修改前）：XLR 56,836 / 60,800（93.5%），RAM10 237 / 256，DSP 117 / 160，最差 setup 余量 +0.220 ns。

## 与 SCU09 的差异

- 去掉 `StyleCam_uart` 主机调试协议（拆出 `sc_engine`）与 `sc431hai_setup` 状态机；串口改由 RISC-V 控制台使用。旧工具 `camera_monitor.py`、`program.py` 的 SCU09 校验不适用于本版。
- DDR AXI 去掉同时钟跨域桥（ASYN_AXI_CLK=0），CSI 像素 FIFO 4096→1024；这两项历史优化合计节省 RAM，单项深度变更以当前综合报告为准。
- `rtl/stylenet_top.v` 的权重/系数 RAM 不带初值（由 CPU 装载）。
- 历史 SCU09 发布包保留；Flash 地址 0 已固化当前 RISC-V 水平镜像版，模型仍位于 0x200000。
