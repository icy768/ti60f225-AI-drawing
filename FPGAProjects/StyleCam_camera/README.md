# StyleCam 摄像头整机 — V21b / SCU09

当前工程：V21b 三风格网络，SCU09 固件，640×480 输入输出；已完成数值对拍、完整编译及临时 JTAG 实际摄像头板测。
当前烧录文件：[已验收 BIT](../烧录文件/20261006_SCU09_V21b_摄像头版/StyleCam_SCU09_V21b_SC431HAI_640x480.bit)，发布包：[V21b / SCU09](../烧录文件/20261006_SCU09_V21b_摄像头版/README.md)。
完整结论见 [V21整合验收报告](results/V21整合验收报告.md)；屏幕/按键反馈另存 results/visual_acceptance.json。

## 链路

SC431HAI 1920×1080 RAW10 → 中央裁剪/2×2 BGGR/黑电平16/原 Gamma → 640×480 RGB 输入双缓冲 → V21b 13层网络与板内 IN → 输出双缓冲 → HDMI 1080p60。
开机梵高，KEY3：梵高 → 浮世绘 → 水墨山水 → 梵高。首次使用风格要完整 IN 校准，后续逐帧轮换更新 IN 层。
模型文件全部来自 ../StyleCam/rtl/gen/v21b_ukiyoe_qat900_640x480，层 R/S/K 与 Q40 IN 常数同步更新。这条整机链路全 RTL 自主执行，不依赖 CPU/ELF 或电脑上传图片/IN 系数。

## 入口

- ti60f225_oob.xml：完整 Efinity 整机工程。
- build.py interface/map/pnr/pgm：ASCII 临时镜像编译，产物回收到本目录 outflow。
- sim_video_engine.py：三风格真实网络及动态 IN 对拍；sim_in_math.py：VGA/极端输入 IN 数学。使用已安装 Torch 的 D:\Anaconda\envs\pytorch_env\python.exe。
- sim_camera.py、sim_display_pressure.py：摄像头/帧保护及显示压力。
- check_camera_report.py：模型、镜像、仿真、资源、时序与位流门禁。
- program.py ram：临时 JTAG；调试阶段不固化。
- camera_monitor.py：SCU09 实际摄像头计数、帧率、板内耗时和欠流粘滞标志。
- package_release.py：生成与门禁匹配的 V21b 烧录包。

V21b / SCU09 已固化至 Flash 地址 0，1,058,000 字节独立回读逐字节一致；配置复位后 SCU09 自动启动和摄像头计数检查通过。RESET_N 或断电后会自动加载 V21b 并启动摄像头，默认梵高。KEY0 复位当前逻辑，KEY3 切换风格。
已验收旧基线源码保存在本机 ../_archive/恢复资料_20261006/历史工程源码与验收摘要_20261006.zip 的 StyleCam_v8_camera_SCU08_V6 目录中，旧烧录包仍在相邻烧录文件目录。

## 克隆仓库后

使用已验收发布包可以直接下载；源码编译需 Efinity 2026.1（build.py 的安装位置按本机修改）。
仿真需在 ../tools/iverilog/mingw64/bin 配置 Icarus Verilog 13.0；网络与 IN 对拍使用有 NumPy、PyTorch、Pillow 的 Python 环境，串口工具还需 pyserial。
输入摄像头无需本地数据集；离线图片测试使用 --image 指定文件。原始日志、Flash 备份、完整仿真向量和历史工程在本机 ../_archive 中保留。
GitHub 保存 RTL、匹配模型、脚本、BIT/HEX 及验收摘要；完整构建的 outflow 中间产物不提交。
check_camera_report.py 核对本机重新生成的编译镜像和报告，不能仅凭克隆的历史摘要证明新构建通过。
