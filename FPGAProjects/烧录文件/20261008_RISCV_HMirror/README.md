# RISC-V 水平镜像版 — 2026-10-08

FPGA ID：`53430a04`。仅增加 SC431HAI 水平镜像 `3221=06` 和匹配的 GBRG 转换。

曝光维持原值 `00/46/00`（1120 半行），模拟增益维持 `83/20`（6.16 倍），R/G/B 使用原 Gamma。保留 RISC-V 权重加载、三种风格、三种布局、按键和 OSD。

位流 SHA256：`3553c9d15a5b54fe920597ed334c9162e637006fad3229892b1ae2a470a9c6b2`。

本机唯一工程入口：`C:\Users\lingye\Desktop\FPGA\FPGAProjects\StyleCam_camera\ti60f225_oob.xml`。从 `StyleCam_camera` 目录执行 `.\program_ram.ps1 -UartPort COM19` 可临时加载本包；Efinity 安装位置可用 `-EfinityHome` 指定。JTAG 加载断电失效，当前未写 Flash。

权重不包含在位流中，板上配置 Flash `0x200000` 需保留 `StyleCam_camera/model/net_blob.bin`（4050 条记录、48616 B、CRC32 `373deed7`）。

详细记录见 `../../docs/目录统一与水平镜像_20261008.md` 和 `checked_build.json`。
