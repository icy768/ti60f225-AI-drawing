# Ti60F225 摄像头与三风格 AI 绘画

当前开发版本为 **RISCV10 / V21b**，ID `53430a0a`，开发集成分支 `develop`。SC431HAI → 原生 BGGR 与 Gamma → 640×480 RGB 水平翻转 → DDR 四输入银行 → 13 层 INT8 CNN 150MHz → DDR 三输出银行 → HDMI 1080p60。

用户已 RAM 下载；40 秒实机采样为 **29.99～30fps、零新增跳帧，三次 UART 风格切换最大 52.534ms**，错误和下溢计数为 0。此证据覆盖分屏布局和短时运行。**本次用户要求跳过 Flash 固化；RISCV10 尚未验收掉电启动**，RISCV08 保留为已固化恢复基线。

| 入口 | 用途 |
|---|---|
| [完整整机](FPGAProjects/StyleCam_camera/README.md) | 唯一 Efinity 入口 `ti60f225_oob.xml`，操作与构建 |
| [RISCV10 下载包](FPGAProjects/烧录文件/20261015_RISCV10_LowLatency_Candidate/README.md) | BIT/HEX、资源、最终时序、八组回归及实机日志 |
| [资源复核与 30fps 来源](FPGAProjects/docs/资源复核与30fps来源_20261015.md) | 提频、末层并行、真实处理分辨率与资源解释 |
| [低延迟实现](FPGAProjects/docs/低延迟与帧调度优化_20261015.md) | 跨时钟、缓存保护和验证边界 |
| [RISCV08 恢复包](FPGAProjects/烧录文件/20261009_RISCV08_BGGR_RGBMirror/README.md) | 历史 Flash 固化验收基线 |
| [训练与导出](FPGAProjects/StyleCam/README.md) | V21b 训练、量化与模型 |
| [独立摄像头参考](FPGAProjects/sc431hai_hdmi/README.md) | 保持原例程 |

K0 切布局；KEY3 短按释放切风格、长按约 0.7 秒切布局。UART `0/1/2` 选风格、`v` 切布局、`s` 状态、`c` 摄像头回读，默认 COM19、115200 8N1。当前资源 XLR58284/60800、RAM10 245/256、DSP145/160，setup +0.278ns、hold +0.026ns。

当前 CNN 实际处理仍是 640×480@约30fps，HDMI 1080p60 表示显示时序；尚未实现真实 1280×720@30fps。旧 RISCV09 调试包已清理，记录见 [清理清单](FPGAProjects/docs/调试包清理_20261015.json)。

语音切风格与手机预览的源码已集成，见[审查与资源复核](FPGAProjects/docs/创意交互审查与资源复核_20261015.md)。候选资源 XLR58940/60800、RAM10 253/256、DSP145/160，最终 setup +0.288ns、hold +0.026ns。新增功能尚未上板；默认下载入口仍为上述已验收 RISCV10 包，本次没有写 Flash。
