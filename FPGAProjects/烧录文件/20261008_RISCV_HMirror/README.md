# RISC-V 水平镜像固化版 — 2026-10-08

ID `53430a04`。仅水平翻转改变画面方向：`3221=06`、GBRG。曝光 `00/46/00`，模拟增益 `83/20`，数字增益 `00/80`，R/G/B 使用原 Gamma；绿色倍率 1。未启用额外 AE/AWB。

包含启动 Flash 唤醒修复（0xAB）和串口只读诊断 `c`。保留 RISC-V 调度、三种风格、三种布局、按键与 OSD。

- BIT SHA256：`e3a4f17c8532d7634bbcc8fee03fa1c615c9fbd638a41564d1100cecb63f0c54`
- HEX SHA256：`d9e1763a6a8c27d6cbb943cbe33c18ee4d523642b34b1f65ed0e74e5d7537f76`
- 固件大小：9834 字节。
- 固化状态：已复位，从 Flash 自主启动验收通过。
- 配置 1050510 字节独立回读一致；权重 48616 字节回读一致，CRC32 `373deed7`。

唯一工程：`C:\Users\lingye\Desktop\FPGA\FPGAProjects\StyleCam_camera`。临时加载 `.\program_ram.ps1`，固化 `python program_flash_mirror.py`，固化后复位验收 `.\verify_flash_boot.ps1`。串口 COM19，115200 8N1。

详细记录：`../../docs/固化烧录与恢复复核_20261008.md`、`checked_build.json`。板上 Flash `0x200000` 需保留项目 `model/net_blob.bin`（4050 条记录）。
