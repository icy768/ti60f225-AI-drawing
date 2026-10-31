# RISCV11 创意交互正式版（2026-10-31）

在 [10-30 手机预览版](../20261030_RISCV11_PhonePreview_Release/README.md)基础上增加 **Resize 单独演示、风格混合（插值）、手机控制页升级、多手机扫码观看**，并修正摄像头帧率显示。网络仍为 V21b（`net_blob.bin` 48,616 B，CRC `373deed7`），卷积权重、IN 规则、自动曝光不变；ID 仍为 `53430a0b`，以本目录清单和 SHA256 区分。

| 项目 | 结果 |
|---|---|
| 时序 | setup +0.302 ns，hold +0.026 ns |
| 资源 | XLR 57256 / 60800（94%），RAM10 255 / 256，DSP 145 / 160；固件 RAM 16368 / 16384 B（只剩 16 B） |
| 仿真 | 显示 7 种布局逐像素一致、无欠载；手机截图 6 种布局逐像素一致；风格混合 10 组与参考模块逐位一致；混合关闭时 V21 整机回归（3 风格 6912 像素、936 个 IN 系数）逐位一致 |
| RAM 板测（[记录](board_acceptance_20261031.json)） | 手机交互约 11 分钟：三风格、梵高→浮世绘 / 梵高→水墨各档混合、布局与 Resize 切换；fps 29.99～30.01，跳帧 0，各错误计数 0，AE I²C 错误 0；手机预览 14～16 帧/s |
| Flash 固化（[记录](flash_deployment.json)） | 写前双读备份、模型区核对；写后整片独立回读一致，模型区不变 |
| RESET_N 自主启动 | 通过：按 RESET_N 后从 Flash 启动，30.00 fps、三风格就绪、各错误计数 0（见 `flash_boot.log`；启动横幅未录到，运行状态已确认为新固件） |
| 未验 | 物理断电重启、长时间压力测试、4 台手机同时观看 |

## 新增功能

| 功能 | 操作 | 说明 |
|---|---|---|
| Resize 单独演示 | 手机"Resize 缩放"或串口 `z`；`v` / 切换布局退出 | 不经网络直接显示 Resize 输出的 640×480 原图，循环 1x（640×480）→ 1.5x（960×720）→ 2x（1280×960）；推理照常运行，30fps |
| 风格混合 | 手机"风格混合"滑条，或串口 `b T A`（T 目标风格 0～2，A 0～8） | 当前风格的 IN γ/β 向目标风格线性混合 A/8；卷积权重共享，得到真实的中间风格。逐层轮换刷新，约 0.4 s 过渡完成；点任一风格即清除 |
| 手机控制页 | 浏览器打开 `http://192.168.4.1/` | 中文界面：风格卡片、混合滑条、拍照 / 3 秒拍照、录像、风格轮播、扫码观看；作品文件名带时间和风格 |
| 多手机观看 | "扫码观看"或打印 [二维码卡片](../../StyleCam_camera/wifi_stream/docs/stylecam_qr_card.png) | 推流最多 4 台手机同时观看；第 5 台接入时替换最早的连接 |
| 摄像头帧率显示 | — | 由截断改为四舍五入，显示 30.0（统计窗口偶尔多计 1 帧时会闪现 31.0） |

## 接线

与 10-30 版相同（J7 映射）：ESP32 `GPIO17` → 子卡 `J28-37`（FPGA `uart_rx`）；子卡 `J28-39`（`stream_tx`）→ ESP32 `GPIO18`；VC-02 `TX1` → ESP32 `GPIO16`。**电脑 FTDI 串口只能看日志**。

## 文件

| 文件 | 用途 |
|---|---|
| `StyleCam_RISCV11_Creative.bit / .hex` | FPGA 位流（RAM 下载 / Flash 固化） |
| `esp32/esp32s3_stream_creative.ino.bin` | ESP32 应用分区，写 `0x10000`；引导程序与分区表沿用 [J7 包](../20261021_ESP32_VC02_J7_Integration/README.md) |
| `manifest.json` | 文件、源码哈希、时序、资源和状态 |
| `three_styles_ram.log`、`esp32_link.log`、`flash_*.log` | 板测与固化原始日志 |

## 使用

```powershell
cd C:\Users\lingye\Desktop\FPGA\FPGAProjects\StyleCam_camera
python program_main_ae_flash.py --check-only      # 离线核对，不接触板卡
./program_ram.ps1                                 # 下载到易失 RAM
python program_main_ae_flash.py                   # 固化：备份、写入、独立回读；之后按 RESET_N
# ESP32（COMxx 为 ESP32 板载 COM 口）
esptool --chip esp32s3 --port COMxx write-flash 0x10000 ..\烧录文件\20261031_RISCV11_Creative_Release\esp32\esp32s3_stream_creative.ino.bin
# 恢复 10-30 手机预览版
python program_main_ae_flash.py --release ..\烧录文件\20261030_RISCV11_PhonePreview_Release
```

重新构建：`build.py interface|map|pnr|pgm`（`STYLECAM_PNR_OPTS=max_router_iterations=120`），固件用 Efinity RISC-V IDE 的 GCC 13.4 编译；再 `package_riscv11_release.py package`，板测记录用 `accept`（现场切风格）或 `logs`（已有交互日志）。

**注意**：配置 Flash 的模型区 `0x200000` 与 DDR 权重库试验版共用，测试那一版前需先写回它的模型（备份在 `StyleCam_camera_ddrw/validation/flash_backup_before_v21_20261031/`）。
