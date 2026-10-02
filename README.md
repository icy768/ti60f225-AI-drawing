# Ti60F225 SC431HAI Camera Tone Mapping

本仓库的主工程是当前已完成调试的 SC431HAI 摄像头 tone mapping 工程，基于官方 `Ti60f225_sc431hai2hdmi_v6`。工程说明、改动记录和板测结果见 [README_使用说明.md](README_使用说明.md)。

## Git 协作

- `main`：已验证的摄像头 tone mapping 基线。
- `develop`：队友联调集成分支。
- 每个任务从 `develop` 创建短期功能分支，完成后通过 PR 合并，例如 `fpga/conv-v1`、`ai/model-int8-v1`、`fw/conv-driver`。
- 新模块尚未并入；由对应负责人从 `develop` 建分支提交。不要将已验证的摄像头主工程整体搬动。
- 经板测验证的 bitstream 保存在 `outflow/sc431hai_tonemap_v6.bit`；Efinity 中间产物和个人调试波形不纳入版本控制。

首次构建请使用 Efinity 2026.1 打开 `ti60f225_oob.xml`。团队共享前需将本仓库关联到新项目远程仓库；旧 IMX219 远程与本工程无关。
