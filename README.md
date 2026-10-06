# Ti60F225 摄像头与三风格 AI 绘画

当前已验收整机：**V21b 网络 / SCU09 固件**，SC431HAI 摄像头输入，板内 IN，DDR 双缓冲，HDMI 输出。
整机源码位于 **develop** 分支；main 保留独立摄像头基线。

所有当前工程统一位于 [FPGAProjects](FPGAProjects/README.md)。

| 路径 | 用途 |
|---|---|
| [FPGAProjects/StyleCam_camera](FPGAProjects/StyleCam_camera/README.md) | 当前完整上板工程；Efinity 入口 ti60f225_oob.xml |
| [FPGAProjects/StyleCam](FPGAProjects/StyleCam/README.md) | V21b 网络、训练、量化及成套导出 |
| [FPGAProjects/sc431hai_hdmi](FPGAProjects/sc431hai_hdmi/README.md) | 已调通的独立摄像头例程 |
| [FPGAProjects/烧录文件](FPGAProjects/烧录文件/README.md) | 当前 SCU09 烧录包及 SCU08 恢复包 |
| [FPGAProjects/docs](FPGAProjects/docs/工程整理与验收.md) | 目录、版本和验收索引 |
| [docs/三人协作指南.md](docs/三人协作指南.md) | 分支与提交步骤 |

SCU09 已固化至 Flash 地址 0，1,058,000 字节独立回读完全一致，并通过配置复位后的自主启动验证。
RESET_N 或重新上电自动启动摄像头和风格处理，默认梵高；KEY3 循环切换梵高、浮世绘、水墨山水。
复位后约 30 秒板测：摄像头 30.009 fps，风格输出 15.004 fps，错误和 HDMI 欠流为 0。

历史工程、原始验收日志、Flash 备份及旧 Git 工作区保存在本机 FPGAProjects/_archive；工具二进制在 FPGAProjects/tools。这些本地归档不加入 Git。
发布清单使用仓库相对路径。大数据集、Python 环境、仿真波形和中间构建产物不进入仓库；可直接使用已验收的烧录包。
