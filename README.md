# Ti60F225 摄像头与三风格 AI 绘画

最新交接：[项目交接文档（2026-10-09）](FPGAProjects/docs/项目交接文档_20261009.md)，适用RISC-V 08；包含操作、参数、构建和清理记录。

当前分支 `feat/basic-requirements`：**RISC-V 08 / V21b 三风格网络**。SC431HAI → 原生 BGGR、5×5 插值与原 Gamma → 640×480 RGB 水平翻转 → DDR 三缓冲 → 卷积/ReLU/板内 IN → HDMI 1080p60。RISC-V 负责摄像头初始化、权重加载、调度、中断与串口控制。

用户已确认摄像头画面正常。ID `53430a08` 已固化 Flash；1,073,814 字节独立回读完全一致，RESET_N 后自主启动、模型 CRC 和实时运行验收通过。FPS 约 15，CAM 约 29.9，错误计数为 0。

| 入口 | 用途 |
|---|---|
| [FPGAProjects/StyleCam_camera](FPGAProjects/StyleCam_camera/README.md) | 当前完整整机，Efinity 入口 `ti60f225_oob.xml` |
| [当前 08 烧录包](FPGAProjects/烧录文件/20261009_RISCV08_BGGR_RGBMirror/README.md) | 匹配源码的 BIT/HEX、哈希、资源、时序与固化证据 |
| [摄像头修复与原因判断](FPGAProjects/docs/原生BGGR与RGB翻转验证_20261009.md) | 原生 BGGR、RGB 翻转与画面验收记录 |
| [StyleCam](FPGAProjects/StyleCam/README.md) | V21b 网络、训练、量化与导出 |
| [sc431hai_hdmi](FPGAProjects/sc431hai_hdmi/README.md) | 保持未修改的独立摄像头参考例程 |
| [工程目录与验收索引](FPGAProjects/README.md) | 唯一项目目录、当前操作与历史记录 |

KEY3 循环切换梵高/浮世绘/水墨；KEY2 轮换对比/风格全屏/原画全屏；串口 `0/1/2` 切风格，`v` 切布局，`s` 查状态，`c` 读实际曝光/增益。默认 COM19，115200 8N1，详细命令见整机 README。

唯一开发目录为 `FPGAProjects/StyleCam_camera`。2026-10-06 的全 RTL SCU09 和更早恢复包属于历史基线；本次上传到 `feat/basic-requirements`。历史资料：[10 月 6 日交接文档](FPGAProjects/docs/项目交接文档_20261006.md)、[三人协作指南](docs/三人协作指南.md)。
