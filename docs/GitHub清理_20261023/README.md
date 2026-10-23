# GitHub 分支与 PR 清理（2026-10-23）

仓库：`icy768/ti60f225-AI-drawing`。按用户要求清理已经停用、被替代的分支和合入申请；没有合并代码、改写主分支、删除恢复包或操作板卡。

## 当前结果

- 远端分支由 **9 个减为 4 个**。
- 打开的 PR 由 **4 个减为 1 个**，旧 PR **#3 / #4 / #5 已关闭**。
- 删除前为五个分支建立远端恢复标签，逐一核对原提交；删除使用提交号校验和原子操作。
- 已再次确认删除分支不存在、恢复标签仍在、保留分支仍在，`main` 提交未改变。
- GitHub 关闭 PR 后保留历史页面；没有把关闭当作合并。

## 保留分支

| 分支 | 用途 |
|---|---|
| `main` | 默认主线和既有独立交付；本次不强制覆盖 |
| `codex/release-riscv11-ae-in4-20261018` | 已上板、固化的 RISCV11 正式恢复基线 |
| `codex/consolidated-project-20261023` | 最新工程整理、语音/Wi-Fi、完整 VC-02 SDK 和固件，当前更新入口 |
| `codex/delivery-v21b-fwp1-20261022` | 最新 FWP1 原始冻结网络交付，保留后续对照和上板用途 |

**[PR #6](https://github.com/icy768/ti60f225-AI-drawing/pull/6)保留打开：**已验收 RISCV11 尚未合入 `main`，因此这份正式版合入申请仍有用途。本次没有自动合并。

## 已删除分支与恢复标签

| 已删除分支 | 保留标签 | 原提交 |
|---|---|---|
| `develop` | `archive/20261023/develop` | `0e7774a4e03e35366c4160ada5a1bed5b9307305` |
| `feat/basic-requirements` | `archive/20261023/riscv08-basic-requirements` | `545f3b6a0036ccf8c9305fe47ead505665d414c1` |
| `codex/resource-throughput-20261013` | `archive/20261023/riscv10-resource-throughput` | `80146c4b6efa00f4a43c80222589542ed9c7b68c` |
| `fw/creative-interaction` | `archive/20261023/creative-interaction-legacy` | `c287959ad82302fda03bf6fde96710a7a2c9e435` |
| `codex/tristyle-v4-paired-v5-20261018` | `archive/20261023/tristyle-v4-paired-v5` | `a09d8ec2db9e2743ca2b1d535508b13bb071b1a4` |

RISCV08/RISCV10 已由正式 RISCV11 替代，旧语音/预览方案已由最新交付替代，较大 V5 未作为实时主用。旧交互分支还有独有的手势源码，RISCV10 也有独有固化记录；这些内容均完整留在对应恢复标签，未擅自混入正式版，也没有仅因为“没合并”而丢弃它们。

恢复示例（只操作 Git，不操作硬件）：

```powershell
git fetch origin refs/tags/archive/20261023/creative-interaction-legacy:refs/tags/archive/20261023/creative-interaction-legacy
git switch -c codex/restore-creative-interaction archive/20261023/creative-interaction-legacy
```

较早说明中的旧分支链接应按本表映射到标签或原提交。原有 `stylecam-v21-handoff-20261005`、`stylecam-v6-handoff-20261004` 标签未修改。

## 已关闭 PR

| PR | 原用途 | 关闭原因 |
|---|---|---|
| [#3](https://github.com/icy768/ti60f225-AI-drawing/pull/3) | 旧 RISCV10 语音/预览/手势候选 | 当前语音/Wi-Fi 使用新交付；独有手势源码转标签保存 |
| [#4](https://github.com/icy768/ti60f225-AI-drawing/pull/4) | RISCV10 后续集成 | 由已验收 RISCV11 和最新整理入口替代 |
| [#5](https://github.com/icy768/ti60f225-AI-drawing/pull/5) | 较大 V4/V5 网络候选 | 不作为当前实时主用，完整冻结交付转标签保存 |

当前语音到 FPGA、手机实际预览及三板并发仍待验收；清理分支不改变这些功能状态。未采用的 PE6 资源试验仍留在本地，没有因清理而启用。

最终清理快照见 [result.json](result.json)，原计划和逐阶段核验见同目录 JSON。`result.json`中的整理分支提交号是删除动作完成时的快照；发布本说明会正常推进该分支，不改变四个保留分支的集合。
