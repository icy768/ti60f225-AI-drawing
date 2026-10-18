# RISCV11 自动曝光 / IN4 正式版（2026-10-18）

当前总工程默认下载包，ID `53430a0b`。用户确认自动曝光和三风格画面正常；同一 BIT 重新下载后完成三风格采样，再固化 Flash、独立逐字节回读，并通过实体 RESET_N 自主启动。

- 工程入口：`FPGAProjects/StyleCam_camera/ti60f225_oob.xml`。
- BIT：`StyleCam_RISCV11_Main_AE_IN4.bit`；HEX：`StyleCam_RISCV11_Main_AE_IN4.hex`。
- 55615/60800 XLR、243/256 RAM10、145/160 DSP；setup +0.253ns、hold +0.026ns。
- 原 V21b 三风格、自动曝光；手机预览 / AWB 默认关闭。新网络、手势未集成。
- 三风格分屏采样覆盖 34 秒的板内时间、19 个读数，29.99～30.01fps，运行期无新增 skip，采集 / 显示 / AE I²C 错误为 0。用户另行确认画面正常。
- Flash 地址 0，配置有效载荷 1,053,829 字节；0x200000 的模型 48,616 字节保持不变。500kHz 独立回读完全一致。
- 用户按 RESET_N 后，串口捕获完整启动、模型 CRC `373deed7`、三风格 ready=7 与约 30fps。
- 固件 13746 B，链接 RAM 16080/16384 B（含 2048 B 栈）。

`manifest.json` 绑定位流、源码、最终资源/时序和全部离线回归摘要；`board_acceptance_20261018.json`、`three_styles_ram.log` 记录 RAM 验收，`flash_deployment.json`、`flash_boot.log` 及 `flash_*.log` 记录固化证据。厂商第一次快速校验失败后自动降速重试成功，随后另做独立回读。

在整机目录执行 `./program_ram.ps1 -CheckOnly` 或 `python program_flash_release.py --check-only` 可离线检查。去掉检查选项会分别下载 RAM 或重写配置 Flash；模型区由固化工具保护。RISCV10 / RISCV08 恢复资料保留。

本次范围为三风格、分屏和短时运行，物理断电重启、全部布局与长时间压力测试仍待补验。历史离线候选说明保存在 `offline_build_readme.md`，其中“待上板”仅指原 10 月 17 日构建时状态。
