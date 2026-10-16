# StyleCam_camera：SC431HAI 实时 AI 绘画整机

这是摄像头、DDR、FPGA 网络推理、RISC-V 控制和 HDMI 显示的完整整机目录。唯一 Efinity 工程入口为 **`ti60f225_oob.xml`**。项目架构、分支和完整进度以[根 README](../../README.md)与[当前进度](../docs/赛题指标与完成情况_20261015.md)为准。

## 先选择正确版本

| 分支 | 源码状态 | 验收情况 |
|---|---|---|
| `main` / `develop` | 既有 SCU09 主线，本轮仅整理文档 | 不包含后续 RISCV10 功能源码 |
| `feat/basic-requirements` | RISCV08 / `53430a08` | 已固化，Flash 独立回读和复位自主启动通过，作为恢复基线 |
| `codex/resource-throughput-20261013` | RISCV10 / `53430a0a` | RAM 采样通过；2026-10-16 Flash 固化、独立回读及配置复位自主启动通过 |
| `fw/creative-interaction` | RISCV10 + 语音 / Wi-Fi 预览候选 | 代码和离线验证完成，尚未上板、尚未合并 |

当前按用户安排保留分支，等待实际硬件验证后再合并。本目录 README 说明项目整体进度，不代表任意分支的源码或下载脚本都相同。

## 当前 RISC-V 主链路

SC431HAI 1920×1080 RAW10 → 原生 BGGR 5×5 MHC 与 Gamma / 手动 RGB 增益 → 中心裁剪及 2×2 平均 → 640×480 RGB 水平翻转 → DDR 多银行 → V21b 13 层 INT8 CNN / 板内 IN → HDMI 1080p60。

RISCV10 推理域为 150MHz，控制与 DDR 用户域为 100MHz，末层采用 PE12，四输入 / 三输出 DDR 银行。CPU 负责初始化、Flash 模型 CRC 校验与装载、帧任务/中断、UART 和 OSD；模型 blob 保持 48,616 字节，不需要电脑逐帧上传图像或 IN 参数。

## 已有实机结果

RISCV10 在分屏布局下的 40 秒记录为：640×480 处理 29.99～30fps，摄像头约 29.9fps，网络耗时约 32.9～33.2ms；`run_skip=0`、总 skip 不增加、错误和欠流为 0。三次 UART 切换到 HDMI 换帧确认最大 52.534ms，不包括显示器发光延迟。

此结论不覆盖长时间运行、各布局和全部实体按键操作。RISCV10 已于 2026-10-16 固化，1075167 字节独立回读一致，配置复位后的完整自主启动与约30fps运行通过；未单独做完整断电周期。RISCV08 仍保留为历史恢复基线。当前语音 / 手机预览候选没有新增实机运行结论。

## 控制与下载入口

K0 循环切换分屏、风格全屏、原画全屏。KEY3 短按释放切风格，长按约 0.7 秒切布局。RISC-V 版本 UART 为 115200 8N1：`0/1/2` 选风格、`v` 切布局、`s` 状态、`c` 摄像头回读，串口号按实际枚举选择。

- [RISCV10 下载包与实机日志](https://github.com/icy768/ti60f225-AI-drawing/blob/codex/resource-throughput-20261013/FPGAProjects/烧录文件/20261015_RISCV10_LowLatency_Candidate/README.md)
- [RISCV08 固化恢复包](https://github.com/icy768/ti60f225-AI-drawing/blob/feat/basic-requirements/FPGAProjects/烧录文件/20261009_RISCV08_BGGR_RGBMirror/README.md)
- [创意交互候选接线及固件](https://github.com/icy768/ti60f225-AI-drawing/blob/fw/creative-interaction/FPGAProjects/StyleCam_camera/wifi_stream/README.md)
- [候选代码审查、资源与时序证据](https://github.com/icy768/ti60f225-AI-drawing/blob/fw/creative-interaction/FPGAProjects/docs/创意交互审查与资源复核_20261015.md)

使用下载脚本前先确认当前分支和目标包。RISCV10 的 `program_ram.ps1 -CheckOnly` 仅核对包；默认包不含新增预览功能。候选上板需使用本次构建生成的候选 BIT，不能把旧包下载成功当作新功能验收。2026-10-16 已完成基础 RISCV10 的 Flash 写入与复位启动验收；该结果不适用于语音/手机预览候选。

## 构建与验证

在所选 RISC-V 工程分支下，`build.py interface / map / pnr / pgm` 分别执行接口、综合、布局布线和位流生成；`STYLECAM_EFINITY` 指定工具目录，`STYLECAM_BUILD_DIR` 指定 ASCII 构建镜像目录。RISC-V 固件位于 `embedded_sw/soc/software/standalone/stylecam/`；重建 ROM 后应与对应源码和模型成套核对。

RISCV10 的 XLR/RAM10/DSP 为 58284/245/145；交互候选为 58940/253/145，最终最小 setup/hold 为 +0.288/+0.026ns。候选的 `sim_stream.py` 覆盖小光栅、FIFO 溢出恢复和实际 1080p60 光栅；`wifi_stream/tools/check_host.py` 是主机检查，不等于 ESP32 原生构建。

历史交接文档和旧下载包各自保留原有版本范围。当前板级接线、寄存器操作和恢复流程应结合所选分支的说明，不能把 SCU09、RISCV08、RISCV10 和交互候选混为同一发布。
