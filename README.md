# Ti60F225 摄像头与三风格 AI 绘画

本地 Git 仓库统一放在 `C:\Users\lingye\Desktop\FPGA`。不要在另一个目录重复维护同名源码副本。

| 目录 | 用途 |
|---|---|
| sc431hai_hdmi | 用户已跑通的独立摄像头工程，入口 ti60f225_oob.xml |
| FPGAProjects/StyleCam | v21b 三风格网络、固件和视觉子系统，入口 syn/vision_map.xml |
| docs | 协作步骤、整理说明和本轮 PC 检查结果 |

长期分支保留 main（摄像头基线）和 develop（网络与整机集成）；交付分支合并后删除。当前清理提交若尚未发布，以 docs/本地整理状态.md 为准。

日常从当前目录执行 `git fetch origin --prune`、`git switch develop`、`git pull --ff-only origin develop`。修改前从最新 develop 建短期功能分支，PR 审查后合入并删除功能分支。

独立摄像头与网络子系统尚未完成视频尺寸/BSP/DDR 的整机统一。本轮只做源码整理和 PC 检查，不做上板验证。
