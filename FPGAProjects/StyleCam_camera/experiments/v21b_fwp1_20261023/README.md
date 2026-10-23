# 2026-10-23 新版网络效果复测

固定来源：GitHub `icy768/ti60f225-AI-drawing` 的 `codex/delivery-v21b-fwp1-20261022`，提交 `7d95dbeaf9b3e9545814be7081390c2f79f2c727`。选定候选为 `D1B60_B_FWP1`。

## 结论

新版主要改善梵高的颜色。人物样图中脸部蓝绿偏色减轻；摩托车红色更接近输入，整体颜色更柔和。同时局部纹理变软，细碎纹路仍多，未见完整解决随物体组织的弯曲笔触与颜料块问题。湖面、草地仍存在明显的风格性改色。属于有限画质改进。

浮世绘和水墨没有更新：参数检查确认只改梵高的 IN gamma/beta，四种场景下其余两种风格合计 8 例均逐像素一致。

## 本轮实际完成

- 下载 54 个评估及完整选定候选文件，共 9,214,426 字节；逐一核验固定提交的 Git blob SHA1，并记录 SHA256。
- 核对选定候选完整子清单。未下载并验证上游约 550MB 全包，不宣称全包校验通过。
- 交付 baseline blob 与当前正式工程 blob 字节相同；baseline qparams 全字段与当前正式工程一致。
- 卷积权重、图拓扑、激活尺度及 R/S 不变；仅梵高 IN gamma/beta 改动。
- 从推理 qparams 重建 640×480 动态 IN 常量 ROM，864 个字全部等于最终选定候选；qparams 同目录导出 blob 与最终候选 blob 字节相同。
- blob 为 48,616 字节，CRC32 `20d4d7eb`；新旧固件实际仅 10 字节变化；四个固件 ROM lane 重构与最终固件逐字节一致。
- 人物、湖面、室内摩托车、草地长椅，四种场景 × 三风格 × 新旧版本，合计 24 次 CPU 整数参考推理，输入输出均 640×480，无输出后处理。

## 查看

- [完整三风格对比页](results/index.html)
- [梵高四场景对比](results/comparison_0.jpg)
- [人物梵高原尺寸](results/person_vangogh.jpg)
- [机器可读复测记录](results/result.json)
- [下载来源与哈希](download_verified.json)

每组左为输入，中为当前 RISCV11/V21b，右为新版 D1B60/FWP1。原数据文件 `architecture.png` 实际是室内摩托车，`plants_garden.png` 实际是草地长椅，展示标签按画面内容修正。

## 验证范围

推理使用交付 `source/golden.py` 和本帧 IN 统计，近似静止场景。真实板端有跨帧 IN 更新，动态视频不能直接由静态图保证。本轮没有下载到 FPGA、写 Flash、跑 RTL 或测板端帧率；GitHub 交付文档也将新版标为未经板测及完整 SoC 启动验证。旧版约 30fps 不属于新版实测结果。

原正式工程、固化包和现有修改均保留。评估文件仅在此隔离目录。运行环境为 `D:/Anaconda/envs/pytorch_env/python.exe`，PyTorch 2.13.0+cu126；推理在 CPU 执行。

`fetch_subset.py` 可重复核验/补齐所选下载。`evaluate.py` 进行参数与部署文件核验和推理，默认拒绝覆盖已有 `results`，复跑应在新实验副本中进行。

## 上板准备

用户已在 2026-10-23 明确要求上板烧录。`board_trial.ps1 -CheckOnly` 已通过选定候选完整子清单、模型配对与 Flash 地址不重叠检查：配置 HEX 解码 1,054,559 B，配置备份/可能擦除范围 1,114,112 B，小于模型起始地址 0x200000。此检查不访问硬件。

实际执行入口为 `./board_trial.ps1 -UartPort <确认的FPGA串口>`。脚本枚举唯一 FTDI/JTAG 目标、打开串口，分别双重读取备份当前配置与 64KiB 模型区域；备份一致后才写入匹配的新配置与模型，独立读取比较两个区域，再 JTAG RAM 启动同一新 BIT 并观察 CRC20d4d7eb、ready=7。默认每风格采样 30 秒；失败时尝试恢复并回读原始备份。成功不代表自主 Flash 配置复位、物理断电或三风格各十分钟长稳已验收。没有将上游 board_tested 标志改为 true。

初次及用户确认连接后的枚举均显示 `No USB target detected`，Windows 当时仅存在 CH340 COM29，没有 VID_0403 的 FTDI/JTAG 下载器和原 COM19。等待物理 JTAG 连接解决后继续；当时未执行桥接、Flash 擦写或新 BIT 下载。

**最新用户指令：只检测连接，暂不下载或烧录。** 已停止后续部署动作；`board_trial.ps1` 仅执行过 `-CheckOnly`。重新插拔并进行 Windows 硬件扫描后的最终检查仍为 Efinity `No USB target detected`；CH340 COM29 在线，历史 FTDI/COM19 记录状态为 Unknown/非当前设备。未来不得因 JTAG 恢复连接而自动执行此处烧录流程，需遵循用户后续指令。
