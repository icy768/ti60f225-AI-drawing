# FPGA 工程统一入口

统一工程目录为仓库内的 `FPGAProjects`；后续在这里开发、编译和存放烧录文件。Git 根目录为上一级 FPGA，main 保存当前稳定版，develop 用于后续开发。

| 目录 | 用途与状态 | 工程入口 |
|---|---|---|
| [StyleCam_camera](StyleCam_camera/README.md) | **当前整机工程：V21b / SCU09**；摄像头、板内 IN、DDR 双缓冲、HDMI、KEY3 | `StyleCam_camera/ti60f225_oob.xml` |
| [StyleCam](StyleCam/README.md) | V21b 训练、量化与网络源码；整机使用同版导出参数 | `StyleCam/syn/vision_map.xml` 是交付视觉子系统入口 |
| [sc431hai_hdmi](sc431hai_hdmi/README.md) | 独立 SC431HAI 摄像头基线，曝光 1120 半行 | `sc431hai_hdmi/ti60f225_oob.xml` |
| [烧录文件](烧录文件/README.md) | 当前 V21b 与旧 V6 恢复包分别保存 | `.bit` 临时下载，`.hex` 固化（当前已完成） |
| [_archive](_archive/README.md) | 本地恢复资料：历史源码压缩包、Git 提交备份和厂家例程 | 当前版本从 StyleCam_camera 开始 |
| tools | 共用 Icarus Verilog | `tools/iverilog/mingw64/bin` |

## 当前下载与固化文件

工程产物：`StyleCam_camera/outflow/ti60f225_oob.bit`。
发布副本：[StyleCam_SCU09_V21b_SC431HAI_640x480.bit](烧录文件/20261006_SCU09_V21b_摄像头版/StyleCam_SCU09_V21b_SC431HAI_640x480.bit)。
固化使用：[StyleCam_SCU09_V21b_SC431HAI_640x480.hex](烧录文件/20261006_SCU09_V21b_摄像头版/StyleCam_SCU09_V21b_SC431HAI_640x480.hex)。
SHA256：`83ffe2006540cb03bd2321ad7e4f64063226b892cce610a5014463f934f27d14`。

临时 JTAG 验收及固化后启动均已读到 SCU09，板上标识 `534355098002e0011b00030d`；摄像头与 IN 自动运行，无需电脑上传照片或系数。
V21b / SCU09 已固化至 Flash 地址 0，1,058,000 字节独立回读逐字节一致；配置复位后 SCU09 自动启动和摄像头计数检查通过。RESET_N 或断电后会自动加载 V21b 并启动摄像头，默认梵高。KEY0 复位当前逻辑，KEY3 切换风格。

## 已完成检查

- 三风格真实 13 层网络：9 帧、6,912 像素、936 IN 系数完全一致，含无复位切换、动态 IN 更新和背压。
- IN 数学：3,273 组，含 VGA 实景、随机、全黑、全白，与交付金标准完全一致。
- 摄像头适配、输入保护、帧调度、输出双缓冲及显示压力复验通过；压力场景 81,920 个像素一致、欠流 0。
- 完整编译通过：XLR 57,258/60,800，RAM10 252/256，DSP 117/160；setup +0.172 ns，hold +0.012 ns。
- 最近板测 30.39 秒，风格输出 15.004 fps，传感器 30.009 fps；捕获/处理/AXI/欠流错误 0，复位以来没有 HDMI 欠流。
- 单次稳定板内网络约 58.69 ms。第一次使用某风格需完整 IN 校准，画面切换会有首次校准等待。

最近板测请求风格索引：[0]；用户已确认三种风格正常且 KEY3 切换返回梵高，反馈保存在 StyleCam_camera/results/visual_acceptance.json。
实际证据：[整合验收报告](StyleCam_camera/results/V21整合验收报告.md)、results/offline_check.json、validation/ram_programming.json、results/camera_video_latest.json。

## 开发与下载

在 StyleCam_camera 内使用 `D:\Anaconda\python.exe -B build.py interface`，再依次 map、pnr、pgm；ASCII 临时编译镜像用于规避工具的中文路径问题，最终产物保存回当前工程 outflow。
`D:\Anaconda\python.exe -B check_camera_report.py` 做版本、仿真和时序门禁；`program.py ram` 临时下载。
网络/IN 数学仿真使用已安装 Torch 的 `D:\Anaconda\envs\pytorch_env\python.exe`。原交付 .venv 记录了其他电脑的 Python 路径，本机使用已有 pytorch_env。
网络参数从相邻 StyleCam 的 V21b 整套导出接入。板级链路沿用已验收 RTL，板内 IN 常数与层移位同步更新；这条整机架构为全 RTL 自主执行，不依赖 CPU/ELF。

目录归档与提交范围见 [工程整理与验收](docs/工程整理与验收.md)。
