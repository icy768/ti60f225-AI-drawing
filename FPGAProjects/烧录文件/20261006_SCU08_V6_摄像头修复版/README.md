# SCU08 / V6_cal100 摄像头已验收烧录文件

本包是 2026-10-06 已确认正常显示的 SC431HAI 三风格摄像头版本。网络仍为 V6_cal100，**不是新拉取的 V21b 网络**。

- `StyleCam_SCU08_SC431HAI_640x480.bit`：临时 JTAG 下载。
- `StyleCam_SCU08_SC431HAI_640x480.hex`：供后续 Flash 固化，地址 0；本次整理未固化。
- 完整可开发工程：`../../_archive/StyleCam_v8_camera_SCU08_V6/ti60f225_oob.xml`。
- 位流 SHA256：`b22ae6140ab036bfe14c23bb624bd73f01f58644d8fdda33f1f35db2a2070660`。
- HEX SHA256：`95265e41e15762583db8f930e7a933531a7760e717a95c0922470f91e1d9e8a7`。
- 原始烧录和验收记录保留在工程 validation/results；Flash 上一次固化仍为 SCU07。

文件路径与版本见 manifest.json。后续新版本必须单独生成发布目录，不能把当前 V6 位流标成 V21。
