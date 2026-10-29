# 三板联调验收：Ti60F225 + ESP32-S3 + VC-02（2026-10-30）

本文记录 2026-10-30 首次完成的三板实物联调。**三条链路已全部打通**：FPGA 预览上行、
ESP32 控制下行、VC-02 语音输入。以下数据均为当晚实物实测，不是仿真或推算。

## 1. 结论

| 链路 | 方向 | 结果 | 证据 |
|---|---|---|---|
| 预览 | FPGA `stream_tx` → ESP32 GPIO18 | 通过 | 手机 `frames=7670`，缩略图实时刷新 |
| 控制 | ESP32 GPIO17 → FPGA `uart_rx` | 通过 | FPGA 串口日志 `style 0→2→1` |
| 语音 | VC-02 `TX1` → ESP32 GPIO16 | 通过（用户确认） | 见 §5.1 归因说明 |

主链路未改动：FPGA 仍为 RISCV11 AE / IN4 正式版，本次只下载了启用预览的 J7 候选到 RAM。

## 2. 三块板状态

### FPGA（Ti60F225 V4）

下载的候选：`烧录文件/20261021_ESP32_VC02_J7_Integration/fpga/StyleCam_RISCV11_J7_Preview.bit`

```
PASS: candidate hashes, J7 pins and routed timing. Setup=0.355ns Hold=0.026ns
JTAG Programming on ftdi://0x0403:0x6011:0:ff/1
Device ID read from JTAG: 0x10660A79
... finished with JTAG programming
```

**只写易失配置 RAM**，配置 Flash 与 0x200000 模型区未被改写。断电后自动回到原正式版，
继续联调需重新下载。

运行状态（板载串口，115200）：

```
[248000 ms] fps=30.00 cam=29.9 nn_ms=33.2 pass_ms=32.3 nn_max_ms=33.4
style=1 view=0 ready=7 proc=7444 cap=7631 skip=186 run_skip=0
caperr=0 vid_err=0 uf=0 hdmi_err=0 irq_err=0
```

30fps 稳定、无采集错误、无 HDMI 欠载、无视频错误。推理与显示链路未受本次接入影响。

### ESP32-S3-N16R8

固件变体 `usb_uart`，经板载 COM 口烧录：

```
Chip type:    ESP32-S3 (QFN56) (revision v0.2)
Features:     Wi-Fi, BT 5 (LE), Dual Core + LP Core, 240MHz, Embedded PSRAM 8MB
MAC:          1c:29:04:22:84:c4
Wrote 16777216 bytes at 0x00000000 in 61.2 seconds
Hash of data verified.
```

### VC-02-Kit

沿用 2026-10-23 烧录的版本 `20261023001`，本次未重烧。音频输出音量偏大，
建议串 8Ω/1W 电阻（见 §5.3）。

## 3. 手机端实测

`http://192.168.4.1/`，SoftAP `StyleCam` / `stylecam1234`：

| 字段 | 值 |
|---|---|
| `frames` | 7670（持续增长） |
| `fps` | 10 |
| `cmds` | 27 |
| `crcErr` | 224（约 3%） |
| `syncLoss` | 7 |
| `heap` | 237640 |
| `psram` | 8306112 |

预览尺寸 96×54 RGB332，UART 3030303 8N1。

## 4. 接线（实物已确认）

| 起点 | 终点 | 参数 |
|---|---|---|
| VC-02 `TX1` | ESP32 `GPIO16` | 115200 8N1 |
| VC-02 `GND` | ESP32 `GND` | — |
| ESP32 `GPIO17` | 子卡 `J28-37`（GPIOL_04 / B3） | 115200 8N1 |
| 子卡 `J28-39`（GPIOL_06 / C3） | ESP32 `GPIO18` | 3030303 8N1 |
| 子卡 `J28-35 或 36` | ESP32 `GND` | — |

子卡为 `EL_001 REV 2.0`（QSE → 2.54mm 2×20，同编号直通），插在主板 J7 上。
各板独立供电，板间 VCC/5V/3V3 不互接。VC-02 供电使用自身 Type-C（5V，>500mA）。

## 5. 问题与处理

### 5.1 语音首次读数异常：`captured` 恒为 8 个 `C0`

**现象**：联调初期 `/voice` 返回
`{"mode":1,"rules":5,"bursts":1,"unknown":1,"last":"","captured":["C0","C0","C0","C0","C0","C0","C0","C0"]}`，
且 `C0` 数量长时间不变、喇叭无声。

**排查**：
- 电脑侧对 CH340（VC-02 自身 USB）以 9600/19200/38400/57600/115200/230400/460800
  七个波特率各读 4 秒，全部 0 字节；
- 拔掉 GPIO18 后 `C0` 依旧，排除 3Mbaud 预览信号串扰；
- 结论指向模块当时未产生识别输出（非接线错误、非波特率错误）。

**处理**：检查麦克风接入与唤醒词使用方式后恢复，最终四条命令可用。

**遗留**：本次未记录恢复后的原始字节，`bursts`/`captured` 的正确读数没有留档。
后续复测时应补一份 `uart_capture.json`（参照
`烧录文件/20261021_ESP32_VC02_J7_Integration/voice/validation_20261023/`）。

### 5.2 手机能看到 SSID 但连不上

热点本身正常（手机可扫到），失败原因是手机在"无互联网"判定后自动断开或切回移动数据。
处理方式：

- Android：弹窗选择「保持连接」，关闭「自动切换移动数据」；
- iOS：选择「保持连接」，必要时关闭「私有无线局域网地址」；
- 连上后不等待"已连接互联网"提示，直接访问 `http://192.168.4.1/`。

另外 ESP32 模组外部的黑色泡棉若遮住板载天线，会出现"能扫到、连不上"，需移开。

### 5.3 语音播报音量过大

软件默认 `default_media_volume=50`（0~100）。改音量需在安信可平台重新生成 SDK，
代价是整个语音版本重刷，答辩前不建议动。

推荐硬件方案：在 `SPK+` 与喇叭之间串 **8Ω/1W** 金属膜电阻，功率降至约 25%（−6dB）。
注意 `SPK−` 不是 GND，不可将喇叭另一端接地。

### 5.4 手机预览模糊、帧率低

不是缺陷，是带宽取舍：

| 分辨率 | 每帧（RGB332） | 3Mbaud 下理论帧率 |
|---|---:|---:|
| 96×54（当前） | 5.2 KB | 58 fps |
| 320×180 | 57.6 KB | 5 fps |
| 640×480 | 307 KB | 1 fps |
| 1280×720 | 921 KB | 0.3 fps |

3Mbaud 有效带宽约 303 KB/s，高清在 UART 上物理不可行。完整画质由 HDMI 1080p 输出承担，
手机端定位是交互验证（按钮、语音状态、画面确实在刷新）。

板载 YT8531SC 千兆 PHY 理论上带宽充足，但 FPGA 侧增加 MAC + UDP/IP 协议栈约需
6000–9000 LUT，而当前 LUT 已 60800/60800、RAM10 254/256，无可用余量；
且赛题要求为"通过 WiFi 模块推流"。故不采用以太网方案。

## 6. 遗留与下一步

1. **补语音原始字节记录**（§5.1），确认 `A1 00 01 01 FF` 系列稳定复现。
2. **降低 CRC 错误率**：当前约 3%。可缩短 J28-39 走线、让地线紧贴信号线、避开 HDMI 排线。
3. **音量**：按 §5.3 串电阻。
4. **断电即失效**：FPGA 候选在 RAM 中，任何断电后需重新执行
   `program_fpga_ram.ps1`，注意脚本默认 `EfinityHome` 为 `D:/ELS/efinity/2026.1`，
   本机 Efinity 路径不同时须传 `-EfinityHome`。
5. **手势**：仍为未启用状态。FPGA 片上实现受资源限制（pnr 失败），ESP32 版本留存于
   标签 `archive/20261023/creative-interaction-legacy`（提交 `c287959`），未并入本分支。

## 7. 复核方式

```powershell
# 离线校验（不访问板卡）
.\esp32\flash_esp32.ps1 -Variant usb_uart -CheckOnly
.\program_fpga_ram.ps1 -CheckOnly -EfinityHome <本机 Efinity 路径>

# 下载 FPGA RAM 候选
.\program_fpga_ram.ps1 -EfinityHome <本机 Efinity 路径>

# 烧录 ESP32（本机无 portable 工具时可用 esptool 直接写 merged.bin）
python -m esptool --chip esp32s3 --port COMx --baud 921600 write-flash 0x0 esp32s3_stream.ino.merged.bin
```
