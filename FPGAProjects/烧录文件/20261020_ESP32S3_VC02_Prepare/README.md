# ESP32-S3 / VC-02 接入准备包（2026-10-20）

2026-10-20 实板补充：已确认 ESP32-S3、16MB Flash、8MB PSRAM，COM 接口版应用可启动。
初版启动程序尝试 QIO 时出现 QIE 设置失败，现已使用官方 DIO 启动程序修正并上板。
**当前下载请使用 [DIO 实板调试包](../20261020_ESP32S3_VC02_DIO_BoardTrial/README.md)**。
本包保留最初编译产物；下方“未烧录 / 未实测”为最初生成时的状态，最新结论见 DIO 包。

适用 ESP32-S3-N16R8，16MB Flash、8MB OPI PSRAM。仅做电脑端准备，未烧录、未实测。
实际连接见 [接线与准备清单](../../StyleCam_camera/wifi_stream/docs/wiring_20261020.md)。

## 内容与状态

| 内容 | 状态 / 用途 |
|---|---|
| ESP32 `usb_uart` 固件 | **原生编译通过**，应用占用 923919 / 3145728 B；USB 转串口口看日志 |
| ESP32 `native_usb` 固件 | **原生编译通过**，应用占用 952763 / 3145728 B；原生 USB 口看日志 |
| `flash_esp32.ps1` | 检查镜像哈希并调用 esptool；`-CheckOnly` 不访问硬件 |
| `usb_control_bridge.py` | 无子卡时由电脑把 ESP32 USB 命令转给 FPGA USB 控制台；只做控制，不传视频 |
| `pyserial-3.5-py2.py3-none-any.whl` | 桥接脚本直接加载，无需安装到全局 Python；PyPI 来源与 SHA 在 `pyserial_source.json` |
| `voice_commands.csv` | 安信可平台逐项填写清单；不是平台导入文件，也不是固件 |
| VC-02 自定义语音 `.bin` | **尚未生成**；本包没有艺术风格词条固件 |
| FPGA 新引脚候选位流 | **完整位流尚未构建**；37 / 39 脚已通过 Efinity interface 检查 |

串口烧录工具已下载到本机：

`C:/Users/lingye/Desktop/FPGA/FPGAProjects/tools/vc02/serial-update-tool/Hummingbird-M-Update-Tool/UniOneUpdateTool.exe`

工具包自带的 `uni_app_release_update.bin` 不是本项目配置的词条固件。
后续应在 [安信可平台](http://voice.ai-thinker.com/)选择 VC-02，按 CSV 配置命令与 HEX，
生成并下载对应的 **`uni_app_release_update.bin`**，再使用该工具串口更新。
完整 JTAG 固件 `uni_app_release.bin` 不能改名冒充串口更新文件。

## ESP32 镜像的选择与离线检查

- `usb_uart`：ESP32 的 USB 转串口接口连接电脑；日志为 115200 8N1。
- `native_usb`：ESP32 的原生 USB 接口连接电脑；启用 Hardware CDC/JTAG 和 USB CDC On Boot。

两种固件的语音 RX 均为 GPIO16、控制 TX 均为 GPIO17、预览 RX 均为 GPIO18。
各目录的 `*.merged.bin` 包含启动程序、分区表和应用，整体从 ESP32 Flash **0x0** 写入。
`*.ino.bin` 是单独应用，不能不带分区 / 启动信息就当成地址 0 镜像使用。

```powershell
./flash_esp32.ps1 -Variant usb_uart -CheckOnly
./flash_esp32.ps1 -Variant native_usb -CheckOnly
```

下列命令会真正写入 ESP32，仅供用户决定开始板测后使用，COMxx 要替换为实际 ESP32 端口：

```powershell
./flash_esp32.ps1 -Variant usb_uart -Port COMxx -ToolRoot C:/Users/lingye/Desktop/FPGA/FPGAProjects/tools/esp32
```

无板阶段没有执行上面这条写入命令。

## 无子卡的电脑桥接

VC-02 TX1 接 ESP32 GPIO16，两板 GND 相连，各自 USB 供电。
ESP32 GPIO17 / GPIO18 暂时留空。FPGA 使用原来已跑通的 USB 串口连接。

```powershell
# 不打开任何端口的自测
python usb_control_bridge.py --self-test

# 用户开始联调后运行，端口号按设备管理器实际值替换
python usb_control_bridge.py --esp-port COM20 --fpga-port COM19
```

PC 必须一直运行桥接脚本。退出脚本或拔掉电脑后，该调试方案不再把命令送入 FPGA。
若后续配齐 QSE 转排针子卡，可按接线清单的 J28-37 / J28-39 准备脱机方案，
并重新构建对应 FPGA 候选。

ESP32 WiFi：`StyleCam` / `stylecam1234`；控制网页 `http://192.168.4.1/`。
语音原始字节接口 `http://192.168.4.1/voice`。没有预览输入时帧计数为 0 属于预期。

## 构建复现

源码使用当前本地工程的 `wifi_stream/esp32s3_stream`，不从 GitHub 未合并分支替换整机。
Arduino CLI 1.5.1、ESP32 core 3.3.2-cn；依赖来源为乐鑫官方国内镜像。
构建脚本用 ASCII 路径镜像，两个变体的设置、源码和镜像 SHA 在 `manifest.json`。

在仓库根目录执行：

```powershell
python FPGAProjects/StyleCam_camera/wifi_stream/tools/build_esp32.py --tool-root C:/Users/lingye/Desktop/FPGA/FPGAProjects/tools/esp32 --output FPGAProjects/烧录文件/20261020_ESP32S3_VC02_Prepare
```

部分 Windows 沙箱会限制 Arduino CLI 的本地目录解析，构建需在能读取工具目录的正常本机终端执行。
编译通过只证明软件能构建；语音词条、引脚、电源、USB 口、PSRAM、无线与三板并发仍需板测。
