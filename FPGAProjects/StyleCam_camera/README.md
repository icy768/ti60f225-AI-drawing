# StyleCam 摄像头整机 — RISC-V 版（分支 feat/basic-requirements）

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

SC431HAI RAW10 → 中央裁剪 / 2×2 BGGR / 黑电平 / Gamma → 640×480 RGB 三缓冲 → V21b 13 层网络与板内 IN → 输出双缓冲 → HDMI 1080p60（布局 + OSD）。
Sapphire（RV32I，16 KB 片上 RAM，100 MHz）：UART0 控制台、SPI0 读配置 Flash、APB3 从口 0（0xF8100000，`rtl/sc_apb_regs.v`）、用户中断 A。

## 上电与操作

1. Flash 0x200000 需有权重包（一次性）：`python flash_blob.py --efinity <Efinity 目录>`（只擦写该处 48 KB，位流区不动，回读比对）。
2. 下载位流后自动运行：装载权重 → 配置传感器（含 5 s 稳定）→ 部署三种风格 → 实时运行，约 8 s。
3. KEY3 / 串口 `0` `1` `2`：风格；KEY2 / 串口 `v`：布局；串口 `s` 状态，`w` 重载权重。串口 COM21（FT4232 C 口），115200 8N1。

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
python -B cpu_monitor.py --port COM21 --boot 25 --seconds 60 --switch
```

仿真（`$env:ICARUS_BIN` 指向 Icarus bin）：`sim_camera.py`（采集三缓冲、调度、显示、APB 寄存器）、`sim_display_pressure.py`（三种布局 90 拍 DDR 延迟下逐像素、无欠流；并复现旧版欠流）、`sim_osd.py`（OSD 逐像素）、`sim_video_engine.py`（权重 RAM 无初值，经 CPU 写口装载全部 4050 条后 9 帧逐位对拍，需 PyTorch 环境，`PYTHONUTF8=1`）。

资源（r4）：XLR 56,836 / 60,800（93.5%），RAM10 237 / 256，DSP 117 / 160，最差 setup 余量 +0.220 ns。

## 与 SCU09 的差异

- 去掉 `StyleCam_uart` 主机调试协议（拆出 `sc_engine`）与 `sc431hai_setup` 状态机；串口改由 RISC-V 控制台使用。旧工具 `camera_monitor.py`、`program.py` 的 SCU09 校验不适用于本版。
- DDR AXI 去掉同时钟跨域桥（ASYN_AXI_CLK=0），CSI 像素 FIFO 4096→1024，共省 42 块 RAM。
- `rtl/stylenet_top.v` 的权重/系数 RAM 不带初值（由 CPU 装载）。
- SCU09 发布包与 Flash 地址 0 处的已固化版本未改动；本版目前只做 JTAG 临时下载。
