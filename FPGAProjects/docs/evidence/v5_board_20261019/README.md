# V5 本地上板试验的公开精简证据

日期：2026-10-19。只包含板测记录与结论，不包含 V5 实验工程、RTL、固件、权重或 BIT。

- `summary.json`：最终资源/时序、位流与模型摘要、三风格测量及后续用户画面反馈；附原始文件 SHA256。
- `r14_first_frame.json` / `r14_first_frame_uart.log`：JTAG RAM 下载、499,072 字节易失 DDR 上传和首帧；ID `53430a0e`。
- `r14_three_styles.json` / `r14_three_styles_uart.log`：每风格 20 秒，核对处理帧与 HDMI 新扫描帧。
- `r13_three_styles.json` / `r13_three_styles_uart.log`：优化前同口径对照；ID `53430a0d`。

原始记录保持不变。自动下载记录生成时尚未收到用户反馈，故 `r14_first_frame.json` 的 `user_picture_accepted=false`；后续用户已确认当前梵高画面正常、能随场景更新，反馈保存在 `summary.json`，没有回写原始文件。其余两个风格没有独立的用户画质验收。

这些短时记录不代表长期压力测试。摄像头约 30fps 与网络实际发布帧率分别统计；本次推理内部 320×240、结果映射至 640×480，不能记作原生 VGA 神经网络推理。AE 开启，AWB、手机预览关闭。Flash 保留 RISCV11。
