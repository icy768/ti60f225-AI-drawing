# 2026-10-23 工程整理记录

唯一项目根目录：`C:\Users\lingye\Desktop\FPGA`。从 [工程入口](../../工程入口.md) 打开当前工程和交付。

## 迁移

- 主工作区原受跟踪文件无未提交修改，先从 `47254c2` 建立本地整理分支 `codex/consolidated-project-20261023`，所有原分支保留。
- 将 `FPGA创新赛` 的 6503 个文件复制/合并到同一相对位置；同名不同内容采用当前最新工作区版本，旧内容先保存到本目录的 ZIP 并校验。
- 复制阶段全部 SHA256 通过；移除重复工作区前再次核验 6462 个源码与数据文件，另 41 个可再生 Python 字节码单列。文件清单和迁移门禁分别为 `active_source_manifest.json`、`removal_gate.json`。
- 移除重复 Git 工作区登记和全部内容。旧目录仅剩空壳，Windows 提示被当前会话占用；没有工程文件残留。
- 原摄像头 ISP 参考移入 `FPGAProjects/reference/sc431hai_isp_v1`，VC02 指南移入 `reference/vc02_guide`，语音准备脚本移入 `StyleCam_camera/wifi_stream/tools`；移动前后逐文件核验，并将该脚本的旧绝对路径改为相对工程位置。详见 `reference_moves.json`。

## 清理

- ESP32 安装包下载缓存已删除；已安装编译器、板卡包和烧录工具保留。记录：`download_cache_removed.json`。
- 删除旧 ESP32 编译镜像、旧 FPGA `_build`、V5 outflow、仿真可执行文件/波形、综合中间网表和 Python 缓存。只删除清单中未受 Git 跟踪的生成物。清单及执行记录：`cleanup_plan.json`、`cleanup_result.json`。
- 原 DEMO 的 7718 个源码/说明/参考文件保存在 `FPGAProjects/_archive/厂家例程_20261023/vendor_sources.zip`；逐成员 SHA256 与 ZIP 完整性通过，排除的 2264 个文件为旧生成物或重复原始摄像头 ZIP。原始摄像头 ZIP 仍在早期恢复归档。常用三份板卡/摄像头 PDF 已另提取到 `reference/board`。
- 交付 ZIP 仅在证明内容全部存在于展开目录、或独有历史说明单独保留后去重。原数据集、checkpoint、模型、RTL/固件、当前正式包、有效历史恢复包和必要构建工具保留。

## 验证与边界

迁移后重新核对正式版 RAM/Flash 检查入口、新版 FWP1 完整候选清单、V5 R13/R14 的冻结源码/发布文件与时序门禁，以及 ESP32/VC02 交付清单。最终结果保存于 `final_validation.json`。

清理不改动正式版的 RTL、模型、固件、IP 或位流。没有烧录、没有修改硬件状态、没有提交/推送或删除 Git 分支。历史记录中的旧绝对路径作为来源证据保留，当前可用入口以根目录的新索引为准。

本目录中的 JSON 和 ZIP 是本机迁移/删除记录；原历史整理文档未用新的结果反写伪造旧证据。
