# J7 子卡语音控制与手机预览候选包（2026-10-21）

2026-10-23 更新：VC-02版本 **20261023001** 已由用户手动烧录。单独USB供电并断开板间线后，电脑通过COM29实测收到四条正确的5字节命令，见 [语音板单板验收](voice/单板验收_20261023.md)。语音播音仍无声，接入ESP32及FPGA尚待验收。完整接线和三板联调见 [操作教程](操作教程.md)。

本次同时发布 [VC-02完整项目SDK与固件说明](voice/sdk/README.md)：554文件的SDK公开归档、逐文件校验清单、配套串口更新镜像及完整镜像。SDK上传副本移除了平台账号密钥，其余源码/库/工具保持原始内容；固件未重编译。

| 项目 | 结果 |
|---|---|
| FPGA | 已从验收过的 RISCV11 / AE / IN4 源码在独立目录完成 interface、综合、布局布线与位流生成 |
| 引脚 | 控制 uart_rx=GPIOL_04/B3/J28-37，预览 stream_tx=GPIOL_06/C3/J28-39；TL 3.3V；板载日志 uart_tx 保留 |
| 预览 | PHONE_PREVIEW=1，96×54 RGB332，UART 3030303 / 8N1 |
| 最终时序 | setup +0.355ns，hold +0.026ns |
| 资源 | XLR 56227/60800，RAM10 244/256，DSP 145/160 |
| 预览仿真 | 7项通过，包括1080p60、溢出恢复、RGB332及快栅格；独立帧解析参考验证通过 |
| ESP32 | 复用已验证的 DIO/usb_uart 固件，16MB Flash、8MB OPI PSRAM；本次镜像 SHA 校验通过 |
| VC-02 | 版本20261023001已烧录；四条语音命令各实测一次，COM29收到20字节，全部与预期匹配。无声问题单独排查，尚未验收VC-02到ESP32 |
| 三板硬件验收 | 未完成；子卡实物针序仍需核实；请按教程分步验收 |

ESP32 GPIO16 收语音，GPIO17 发控制，GPIO18 收预览；控制与语音 UART 为115200 / 8N1。
本次没有改动主工程 RTL、主约束或既有正式镜像。固件与模型沿用 R11；新网络试验没有混入本候选。

离线检查（不接板也能运行）：

```powershell
.\esp32\flash_esp32.ps1 -Variant usb_uart -CheckOnly
.\program_fpga_ram.ps1 -CheckOnly
```

`program_fpga_ram.ps1` 不带 CheckOnly 时会通过 JTAG 下载易失配置 RAM；本包没有自动固化 FPGA Flash 的步骤。
断电会回到原 Flash 程序，需要再次下载候选才会启用子卡新映射及预览。
FPGA ID 仍为 `53430a0b`，要结合包内哈希和下载日志确认候选，不能只凭 ID 判断。

`prepare_voice_update.ps1` 已执行，工具和本项目bin放在 `C:/Users/lingye/Desktop/FPGA/FPGAProjects/tools/vc02/stylecam_update_57fd62fc868b/`。脚本没有启动工具或烧录；换电脑时需先提供厂家工具。

原始固件包、完整SDK压缩包及SDK源码备份位于 `C:/Users/lingye/Desktop/FPGA/FPGAProjects/tools/vc02/stylecam_sdk_20261023001/`。整套SDK保留在本机；本包仅附核对所需源码片段及移除账号密钥后的配置。

下载固件与SDK内更新镜像只有编译时间字符串不同，其余字节相同；本包采用“下载固件”所得文件，SHA256为 `57fd62fc868b0c7be1a22d5032f8573f4b39b9ea29754826b372eecaa5863239`，1217688字节。
2026-10-22 的网页快照保留在本机，不随SDK发布；当天的核对JSON是历史草稿记录。当前固件以2026-10-23下载产物核对记录为准。

构建复现：

```powershell
python FPGAProjects/StyleCam_camera/wifi_stream/tools/build_interaction_fpga.py --build-dir C:/Users/lingye/Desktop/FPGA/FPGAProjects/tools/stylecam_interaction_20261021_rebuild --output FPGAProjects/烧录文件/20261021_ESP32_VC02_J7_Integration_Rebuild/fpga
```

`fpga/manifest.json` 保存源文件SHA、独立候选差异、工具命令、资源、最终时序和文件哈希。
`preview_simulation.json` 保存本次7项仿真结果；`offline_verification.json` 保存本包离线复核结果。

