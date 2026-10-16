# 下载包与恢复资料

下载文件随分支不同，先按[根 README 的版本表](../../README.md)选择源码与配套包。项目使用 SC431HAI，不能混用不同整机版本的 BIT/HEX、固件、模型和清单。

| 版本 | 入口 | 验收范围 |
|---|---|---|
| RISCV10 / `53430a0a` | [下载包与日志](https://github.com/icy768/ti60f225-AI-drawing/blob/codex/resource-throughput-20261013/FPGAProjects/烧录文件/20261015_RISCV10_LowLatency_Candidate/README.md) | RAM 下载后 40 秒 VGA 约30fps、无新增跳帧；2026-10-16 Flash 固化、独立回读和配置复位自主启动通过 |
| RISCV08 / `53430a08` | [固化恢复包](https://github.com/icy768/ti60f225-AI-drawing/blob/feat/basic-requirements/FPGAProjects/烧录文件/20261009_RISCV08_BGGR_RGBMirror/README.md) | Flash 独立回读与自主启动已验收，保留为恢复基线 |
| 语音 / 手机预览候选 | fw/creative-interaction 的本次 outflow 构建 | BIT/HEX 已生成，尚未上板；不能用 RISCV10 旧下载包代替新功能测试 |

当前先进行实际上板验证，暂不合并或删除分支，2026-10-16 已完成基础 RISCV10 的 Flash 固化和复位启动验收；语音/手机预览候选仍待上板。更早的 SCU09、SCU08、RISCV04 等包只代表各自历史版本，继续保留其原始清单与验收范围。
