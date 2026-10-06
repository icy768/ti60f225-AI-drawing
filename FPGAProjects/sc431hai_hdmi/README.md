# SC431HAI → HDMI 独立摄像头例程

这是已调通的独立摄像头工程，用于检查摄像头、CSI、DDR 和 HDMI；当前 AI 风格整机见 [StyleCam_camera](../StyleCam_camera/README.md)。

- Efinity 入口：[ti60f225_oob.xml](ti60f225_oob.xml)。
- 已保留独立摄像头 BIT：[outflow/ti60f225_oob.bit](outflow/ti60f225_oob.bit)。
- SC431HAI 1920×1080 RAW10，实测采集约 30 fps。
- 当前曝光 1120 半行，3E00/01/02 = 00/46/00；黑电平、RGB/Gamma 沿用已调通配置。
- 编译使用 build.py，仿真使用 run_tests.py；运行/采集诊断见 run_video.py、analyze_thumbnail.py、check_capture_pair.py。
- IP、RTL、约束及摄像头初始化表在本工程内，仿真工具集中到 ../tools。

本独立例程不含 V21b 风格网络。当前完整整机的输入输出双缓冲、板内 IN、KEY3 和固化验收属于 StyleCam_camera。
历史调试记录与原始 README 保留在本机 ../_archive/发布前原始记录_20261006/FPGAProjects/sc431hai_hdmi 中；原始验证日志保留在本机 validation。
60 fps 传感器模式尚未验收。此轮整理没有重新编译或下载该独立例程。
