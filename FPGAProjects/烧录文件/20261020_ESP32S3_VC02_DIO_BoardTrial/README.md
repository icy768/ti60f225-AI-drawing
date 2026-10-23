# ESP32-S3-N16R8 DIO 实板调试包（2026-10-20）

实物已通过 COM28 识别为 ESP32-S3 rev 0.2，16MB Quad Flash、8MB OPI PSRAM。
当前使用 `usb_uart` 应用，电脑接开发板标有 COM 的 USB 转串口接口。
`native_usb` 是原生 USB 日志变体，尚未在本次实物上验证。

## 当前验证

- 修改前完整读取原有 16MB Flash 并记录 SHA256，备份在下方板测目录。
- 最初完整镜像写入后通过 esptool 数据哈希校验；应用和 PSRAM 正常启动。
- 该板启用 QIO 时报告 QIE 设置失败，现改用已安装官方 SDK 的 DIO 启动程序。
- DIO 启动程序单独写入 0x0，长度 18,976 字节，esptool 数据哈希校验通过。
- DIO 启动后 QIO 错误消失，45 秒启动采样无 FATAL 或 panic，PSRAM 空闲约 8.31MB。
- 用户已确认手机能连接热点、打开网页和点击风格按钮；后续串口命令计数为 3。
- 没有接入 FPGA 视频，预览帧计数 0 为预期。语音 UART 链路和 FPGA 执行尚未验证。
- 本次没有连接或烧录 FPGA，没有提交 GitHub。

## 镜像来源与边界

应用、分区表复用原生编译并通过 SHA256 校验的
[初版准备包](../20261020_ESP32S3_VC02_Prepare/README.md)。只替换启动程序：
使用同一官方 SDK 的 `bootloader_dio_80m.elf`，经 esptool 5.1.0 生成
DIO / 80MHz / 16MB 启动镜像。已逐字节断言新旧完整镜像从 0x8000 到末尾完全一致，
应用和分区表字节不变。PSRAM 继续使用 OPI，与 Flash 的 DIO 模式分别配置。

完整 Arduino DIO 重编译卡在工具加载库阶段，已停止该编译子进程；
**本包不声称完成新的完整 Arduino 重编译**。`manifest.json` 记录复用来源、
官方 ELF 哈希、各文件哈希和实际打包方式。后续构建脚本已显式加入 `FlashMode=dio`。

## 下载与使用

`flash_esp32.ps1 -Variant usb_uart -CheckOnly` 仅校验包内文件，不访问设备。
实际下载需确认目标是 ESP32-S3、端口对应 COM 接口，再指定 `-Port` 和 `-ToolRoot`。
完整 `*.merged.bin` 长度 16MB，从 0x0 写入，会覆盖整个 Flash；应先保存需要的原程序。
单独 `*.ino.bin` 是应用文件，不能作为地址 0 的完整镜像。

热点为 `StyleCam`，密码 `stylecam1234`，手机连接后打开 `http://192.168.4.1/`。
未接 FPGA 时预览 0 帧属于预期；网页命令表示 ESP32 接收并发出请求，不代表 FPGA 已执行。
语音模块仍为出厂词条时，`5A ...` 数据与当前 `A1 ...` 项目规则不匹配，抓包出现
`unmatched` 可用于验证收到了字节，不代表已经完成风格切换。

## 板测记录

[本次板测、原 Flash 备份及串口日志](../../StyleCam_camera/validation/esp32_standalone_20261020/run_1792464105683/)
包含初版启动、DIO 修正和手机网页操作的观察；最终结论以 `board_validation.json` 为准。
