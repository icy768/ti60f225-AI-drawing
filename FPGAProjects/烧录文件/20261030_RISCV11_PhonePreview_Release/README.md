# RISCV11 AE / IN4 + 手机预览正式版（2026-10-30）

在 [10-18 正式版](../20261018_RISCV11_Main_AE_IN4_Release/README.md)基础上打开手机推流：网络仍为 V21b（`net_blob.bin` 48,616 B，CRC `373deed7`），卷积、IN 规则、自动曝光不变。ID 仍为 `53430a0b`，以本目录清单和 SHA256 区分。

| 项目 | 结果 |
|---|---|
| 时序 | setup +0.187 ns，hold +0.026 ns |
| 资源 | XLR 56518 / 60800，RAM10 255 / 256，DSP 145 / 160 |
| RAM 板测（[记录](board_acceptance_20261030.json)） | 三风格手机切换，50 s 内 fps 30.0～30.0，跳帧 0，各错误计数 0，AE I²C 错误 0；ESP32 收帧 15 帧/s |
| Flash 固化（[记录](flash_deployment.json)） | 写前双读备份、模型区核对；写后整片独立回读一致，模型区不变；RESET_N 自主启动 30 fps、预览正常 |
| 未验 | 物理断电重启、长时间压力测试 |

## 手机预览

- FPGA 按当前布局只截 640×480 风格画（并排布局取右半边，全屏布局取中央；原画全屏时推原画），每 4×4 源像素精确平均为 1 点，输出 **160×120 RGB332**，4×4 有序抖动。
- 一帧分 2 场交错采集（偶数行 / 奇数行），3.03 Mbaud 串口约 15 帧/s。
- ESP32 收齐两段才发布整帧；网页经 82 端口长连接推流（不支持流式读取的浏览器自动退回 `/frame.raw` 轮询），4:3 平滑放大。

## 接线（J7 映射）

| 起点 | 终点 | 参数 |
|---|---|---|
| ESP32 `GPIO17` | 子卡 `J28-37`（GPIOL_04 / B3，FPGA `uart_rx`） | 115200 8N1 |
| 子卡 `J28-39`（GPIOL_06 / C3，FPGA `stream_tx`） | ESP32 `GPIO18` | 3030303 8N1 |
| 子卡 `J28-35/36` | ESP32 `GND` | — |
| VC-02 `TX1` / `GND` | ESP32 `GPIO16` / `GND` | 115200 8N1 |

控制输入已移到 J28-37：**电脑 FTDI 串口只能看日志**，切风格 / 布局用手机网页、语音或板载按键。

## 文件

| 文件 | 用途 |
|---|---|
| `StyleCam_RISCV11_AE_IN4_PhonePreview.bit / .hex` | FPGA 位流（RAM 下载 / Flash 固化） |
| `esp32/esp32s3_stream_previewstyled.ino.bin` | ESP32 应用分区，写 `0x10000`；引导程序与分区表沿用 [J7 包](../20261021_ESP32_VC02_J7_Integration/README.md) |
| `manifest.json` | 文件、源码哈希、时序、资源和状态 |
| `three_styles_ram.log`、`esp32_link.log`、`flash_*.log` | 板测与固化原始日志 |

## 使用

```powershell
cd C:\Users\lingye\Desktop\FPGA\FPGAProjects\StyleCam_camera
python program_flash_release.py --check-only      # 离线核对，不接触板卡
./program_ram.ps1                                 # 下载到易失 RAM
python program_flash_release.py                   # 固化：备份、写入、独立回读；之后按 RESET_N
# ESP32（COMxx 为 ESP32 板载 COM 口）
esptool --chip esp32s3 --port COMxx write-flash 0x10000 ..\烧录文件\20261030_RISCV11_PhonePreview_Release\esp32\esp32s3_stream_previewstyled.ino.bin
```

重新构建：`build.py interface|map|pnr|pgm`（`STYLECAM_PNR_OPTS=max_router_iterations=120`），再 `package_phone_preview_release.py package`、`accept`。
