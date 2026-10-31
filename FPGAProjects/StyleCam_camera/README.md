# StyleCam_camera：SC431HAI 实时 AI 绘画整机

## 当前默认版本：RISCV11 创意交互版（2026-10-31）

唯一 Efinity 总工程入口为 **`ti60f225_oob.xml`**。默认下载包为 [20261031_RISCV11_Creative_Release](../烧录文件/20261031_RISCV11_Creative_Release/README.md)，ID `53430a0b`。在 10-30 手机预览版基础上新增：

- **Resize 单独演示**：view 3/4/5 直接显示 Resize 输出的 640×480 原图，1x / 1.5x / 2x 循环（串口 `z`、手机"Resize 缩放"），推理照常运行（`rtl/sc_display.v`、`rtl/sc_stream_tap.v`）。
- **风格混合**：`rtl/sc_in_refresh.v` 在逐层 IN 刷新时把当前风格的 γ/β 向目标风格混合 A/8（串口 `b T A`、手机滑条），参数经 CTRL[13:12]/[19:16] 与引擎邮箱传入；A=0 时与原逻辑逐位一致。
- **手机页升级与多手机观看**：见 [wifi_stream](wifi_stream/README.md)。
- 摄像头帧率显示四舍五入（30.0）。

RAM 板测约 11 分钟（三风格、混合、布局与 Resize 切换）fps 29.99～30.01、跳帧与各错误计数 0；Flash 写入、整片独立回读与模型区核对通过，RESET_N 自主启动 30fps。物理断电重启和长期压力测试待补验。

预览按当前布局截 640×480 画面（Resize 视图推原图），4×4 精确平均为 160×120 RGB332，分 2 场交错经 3.03 Mbaud 送 ESP32。**控制输入在子卡 J28-37（ESP32 GPIO17），电脑 FTDI 串口只读日志**；上一版为 [10-30 手机预览包](../烧录文件/20261030_RISCV11_PhonePreview_Release/README.md)，不带预览、可用电脑串口控制的旧版是 [10-18 包](../烧录文件/20261018_RISCV11_Main_AE_IN4_Release/README.md)。

当前资源 **57256/60800 XLR、255/256 RAM10、145/160 DSP**；最终 setup **+0.302ns**、hold **+0.026ns**。**固件片上 RAM 16368/16384 B，只剩 16 B**，再加固件功能需先删减；固件必须用 Efinity RISC-V IDE 的 GCC 13.4（`STYLECAM_RISCV_BIN`）编译才能复现。Resize 与片上权重存储见[技术说明](../docs/Resize与权重存储说明_20261023.md)。

## 主链路与本轮改动

SC431HAI 1920×1080 RAW10 → BGGR 5×5 MHC、Gamma / RGB 增益 → 裁剪与 2×2 平均 → 640×480 RGB 水平翻转 → DDR → V21b 13 层 INT8 CNN / 板内 IN → HDMI 1080p60。

RISC-V 和 DDR 用户域 100MHz，推理域 150MHz，末层 PE12，四输入 / 三输出银行。模型 48616 字节，Flash 地址 `0x200000`，CRC `373deed7`。本轮保留三风格、模型、卷积和 IN 数值规则，优化外围译码、计数器、OSD 字库、IN 算术与 epsilon 存储。完整 VGA 307200 像素与参考一致，单帧离线仿真 30.45495ms，不含真实 DDR / HDMI。

自动曝光在 Gamma 前测光，由 RISC-V 每 200ms 按需更新 SC431HAI 曝光和模拟增益，目标亮度 64、死区 56～72，不改变摄像头帧周期。**AWB 默认关闭，手机预览默认开启**。队友新网络和最新手势内容未接入本版。

## 下载与恢复

```powershell
# 检查正式包，不接触硬件
./program_ram.ps1 -CheckOnly
python program_flash_release.py --check-only

# 按实际串口号下载 RAM
./program_ram.ps1 -UartPort COM19
# 固化配置 Flash，保留模型；完成后先开 COM19 监听再按 RESET_N
python program_main_ae_flash.py
# 恢复 10-30 手机预览版
python program_main_ae_flash.py --release ..\烧录文件\20261030_RISCV11_PhonePreview_Release
# 恢复不带预览的 10-18 版
python program_flash_release.py --release ..\烧录文件\20261018_RISCV11_Main_AE_IN4_Release
```

`program_main_ae_ram.ps1` 同样默认正式包，可用 `-ReleaseDir` 指定旧 RISCV11 包；新旧文件名由清单识别。`program_main_ae_flash.py` 是当前 Flash 实现，先备份、再写入和独立回读，记录目录由清单的 `flash_record_dir` 决定。`verify_flash_boot.ps1` 会经电脑串口发命令，只适用于 10-18 版；预览版的控制口已移走，启动验证改为被动读 COM19 日志（见发布包 `flash_boot.log`）。`package_riscv11_release.py package|accept|logs` 负责打包和 RAM 板测记录（`logs` 由已录的交互日志生成）。

RISCV10 恢复入口为 `program_riscv10_ram.ps1`、`program_riscv10_flash.py`、`verify_riscv10_flash_boot.ps1`，配合其历史分支和包使用。RISCV08 的 `program_native_ram.ps1`、`verify_native_flash_boot.ps1` 及恢复包保留。不同包不能混用源码、ROM、模型及位流。

## 操作与构建

控制台（手机 / 语音经 ESP32 转发，115200 8N1）：`0/1/2` 选风格，`v` 切布局，`z` Resize 缩放，`b T A` 风格混合，`s` 状态，`c` 回读摄像头。K0 循环切布局，KEY3 短按释放切风格、长按约 0.7 秒切布局。RESET_N 用于重新装载配置 Flash。

Efinity 2026.1 构建入口为 `python build.py interface / map / pnr / pgm`；`STYLECAM_EFINITY` 指定工具，`STYLECAM_BUILD_DIR` 指定 ASCII 构建镜像。固件源码在 `embedded_sw/soc/software/standalone/stylecam/`，片内 ROM 同步保存在 `fw_rom/` 与 `ip/soc/`。改动硬件或固件后须重新生成配套位流，不能沿用当前已验收哈希。

当前 AE、像素、外围和 IN 回归分别由 `sim_main_ae.py`、`sim_main_ae_firmware.py`、`sim_camera_mhc.py`、`sim_resource_round2.py`、`sim_resource_round3.py`、`sim_in_resource.py`、`sim_in_integrated.py` 等脚本执行。正式包保存离线结果，`validation/release_riscv11_20261018/` 保存本次板测 / Flash / 清理摘要。大体积旧构建镜像已归档，重建旧镜像后可复核历史记录。

## 记录与分支

- [固化与总工程集成记录](../docs/RISCV11固化与总工程集成_20261018.md)：当前实机和 Flash 状态。
- [第四轮 IN](../docs/第四轮动态IN等价优化_20261017.md)、[第三轮外围](../docs/第三轮外围资源优化_20261016.md)、[第二轮外围](../docs/第二轮外围资源优化_20261016.md)、[AE 与第一轮](../docs/自动曝光优先与资源优化_20261016.md)：各自构建时的资源和回归范围；“待上板”是历史状态。
- `feat/basic-requirements`、`codex/resource-throughput-20261013`：RISCV08 / RISCV10 恢复和性能基线。
- `fw/creative-interaction`：语音 / 预览 / 手势扩展保留，最新未验收内容保持独立。
- 队友新网络交付和 `codex/tristyle-v4-paired-v5-20261018` 保留，后续逐步试验。

项目总体架构和完整进度见[根 README](../../README.md)。`sc431hai_hdmi` 保持独立摄像头参考，已移除其中未采用的本地 AE / AWB 原型，并保存完整工作区备份。
