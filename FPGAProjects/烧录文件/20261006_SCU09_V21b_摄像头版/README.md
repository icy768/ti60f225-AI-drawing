# V21b 三风格摄像头整合版 / SCU09

完整工程：[StyleCam_camera](../../StyleCam_camera/README.md)，Efinity 入口 ti60f225_oob.xml。
本包已通过三风格真实网络与动态 IN 对拍、VGA/极端输入 IN、摄像头/双缓冲/显示压力复验、完整编译资源与时序检查。
实际上板结果以工程 results/camera_video_latest.json 和 validation/ram_programming.json 为准。

- `StyleCam_SCU09_V21b_SC431HAI_640x480.bit`：临时 JTAG 下载；SHA256 `83ffe2006540cb03bd2321ad7e4f64063226b892cce610a5014463f934f27d14`。
- `StyleCam_SCU09_V21b_SC431HAI_640x480.hex`：后续 Flash 固化，地址 0；SHA256 `246c29d253d1b5cfc384b0abd1cf2e600bc52e9de69e18983bf6b3f517b483f4`。
- 配置数据长度 1,058,000 字节，区别于 .bit/.hex 的文本文件大小。
- 网络 blob SHA256 `9a1b2382e2c9953f775f5c9c7e5b06fd93e5cad9bcdffa8086dbbe41541a5d5b`。

V21b / SCU09 已固化至 Flash 地址 0，1,058,000 字节独立回读逐字节一致；配置复位后 SCU09 自动启动和摄像头计数检查通过。RESET_N 或断电后会自动加载 V21b 并启动摄像头，默认梵高。KEY0 复位当前逻辑，KEY3 切换风格。
之前的 SCU08 / V6 恢复包保留在相邻目录。
