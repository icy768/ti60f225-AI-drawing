# RISC-V 08：原生 BGGR / RGB 水平翻转（2026-10-09）

当前分支 `feat/basic-requirements` 的已验收整机，ID `53430a08`。用户确认原画正常；Flash 地址 0 的 1,073,814 字节独立回读完全一致，RESET_N 后捕获了完整自主启动日志。模型仍在 `0x200000`，48,616 字节回读一致、启动 CRC `373deed7`。

| 文件 | 用途 |
|---|---|
| [StyleCam_RISCV08_BGGR_RGBMirror.bit](StyleCam_RISCV08_BGGR_RGBMirror.bit) | 临时 JTAG 下载 |
| [StyleCam_RISCV08_BGGR_RGBMirror.hex](StyleCam_RISCV08_BGGR_RGBMirror.hex) | Flash 配置区固化 |
| [manifest.json](manifest.json) | 文件 SHA256、资源、时序、Flash 地址与负载长度 |
| [checked_build.json](checked_build.json) | 匹配源码的 75 个哈希、寄存器、仿真及实板验收 |
| [flash_acceptance.json](flash_acceptance.json) | 固化、独立回读、权重保留与复位启动结果 |
| [自主启动日志](evidence/flash_boot.log) | ID、权重 CRC、191 条摄像头命令、曝光/增益和实时运行计数 |

匹配入口：[StyleCam_camera/ti60f225_oob.xml](../../StyleCam_camera/ti60f225_oob.xml)。源码、固件 ROM 和位流是同一版本；历史 SCU09、RISC-V 04 包可用于历史恢复，当前默认脚本加载 08。

在 `FPGAProjects/StyleCam_camera` 内执行：

```powershell
# 仅临时加载（默认 COM19，Efinity D:\ELS\efinity\2026.1）
.\program_ram.ps1 -UartPort COM19
# 固化前只读门禁；随后固化会备份、写入并独立回读
python -B program_flash_native.py --check-only
python -B program_flash_native.py
# 固化桥占用 FPGA；监听期间按 RESET_N，或重新上电
.\verify_flash_boot.ps1 -UartPort COM19
```

其它电脑使用 `--efinity` / `-EfinityHome` 指定工具路径，并按实际枚举填写串口。位流不含模型权重：新板首次部署需按整机 README 将 `model/net_blob.bin` 写入 `0x200000`。

摄像头采用参考例程的 191 条命令、原生 BGGR、黑电平 16、5×5 MHC 与原 Gamma；曝光 `00/46/00`，模拟增益 `83/20`，数字增益 `00/80`，RGB Q8.8 `256/256/256`。传感器镜像 `3221=00`；左右翻转在 RGB 写 DDR 时完成。640×480 输出和 FIFO=1024 保留。未增加自动曝光或自动白平衡。

原例程 FIFO=4096 会使集成工程使用 271/256 RAM，用户确认采用 1024。本版资源 XLR 60399/60800、RAM10 246/256、DSP 121/160；setup +0.395 ns，hold +0.026 ns。

烧录工具第一次校验出现差异后自动重试成功；最终独立低速回读逐字节一致，复位后启动通过。原配置备份、原始回读 HEX 和权重备份留在本机，不作为新版本发布文件。
