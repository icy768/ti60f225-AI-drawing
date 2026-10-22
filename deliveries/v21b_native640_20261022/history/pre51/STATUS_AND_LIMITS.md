> LATEST50：原固件常量补丁FWP1验证完成，首选候选candidates/D1B60_B_FWP1，BITd05ca9a28994…，仍待20:00监督选择；未完整启动/板测/采纳。GCC15修复仅备选（整份重编译风险）；旧B616e40bb…+D1明确CRC_BLOCKED/研究附件不可启动。原RISCV11回退保留。见evidence/FW_PATCH_RESULT.md与FINAL_DECISION.md。

> LATEST49：旧D1B60_B位流616e40bb…配D1blob会被原固件CRC拒绝，启动BLOCKED。独立CRC修复候选见candidates/D1B60_B_CRC，BIT3f302996…/HEX8fc0a9be…，本地交叉编译+RV32加载器+ROM更新验证，尚未完整启动/板测/采纳；20:00监督选择未定。原RISCV11回退保留。详见evidence/DP3_BLOB_LOAD.md。

# 实测、引用、计算、未验证、未完成

截至2026-10-22 15:03，依据LATEST48。D1B60已通过B级部署证据门，但未经采纳；原RISCV11保留为回退。19:00研究冻结、20:00编译冻结及监督选择交付网络、21–23定稿、23:30交付。用户取消交付前板测。

| 证据类别 | 结果与范围 | 来源 |
|---|---|---|
| 本轮CPU数值实测 | 部署checkpoint SHA、冻结npz/json逐字节相等；18组原生640的整数STE与独立golden 0LSB；CPU/CUDA小图0LSB及有限梯度 | evidence/F0_FIDELITY.md；../F0/RESULT.json |
| 本轮CPU文件核验 | 完整blob48616B，STN1、4050写入与原cfg逐字一致，CRC373deed7与历史启动记录一致；不构成板上Flash SHA回读 | DRAFT_VERIFICATION.json；PARAMETER_BYTES.json |
| 本轮原版整机构建实测 | 正式47254c原版interface/map/PnR完成，56824XLR/243RAM10/145DSP，setup+.240ns/hold+.026ns；未复现历史55615/+ .253ns，该历史精确复现门失败；LATEST48允许对本地原版做B级比较，结果见DP3 | ../DP1/BUILD_REPRODUCTION.md及原始rpt |
| 本轮ROM文件核验 | 基线重新生成所有mem逐字节一致；D1仅270VG gamma/beta字变化，UK/ink/epsilon不变。工具文档支持BRAM初始化更新，但项目patch/readback未验证 | ../DP1/ROM.md；../DP1/ROM_RESULT.json |
| 本轮D1研究算术仿真 | 旧13层conv_layer、5case 48×32，逐层/输出0LSB；未包含自主IN整机，不能代替DP2 | ../R44/D1B60/HG0/ |
| 本轮D1研究视频实测 | 16val+camera30原生640 CPU整数输出，raw/warp比基线.803714/.795645，数值门通过。监督47艺术增量通过，限于色相，纹理变柔 | ../R44/D1B60/expanded/；guidance LATEST47 |
| 本轮J3研究数值实测 | J3_INK和J3_UK_R1各1000QAT/train-export-eval rc0；各18组三风格对J1_60盲页，各3风格×1留出原生640前向抽检0LSB。CC48采用混合、非胜出结论，未独立复看全部 | ../R44/J3_INK/；../R44/J3_UK_R1/ |
| 本轮720隔离核心综合实测 | 640核心138RAM10/141DSP；1280核心219RAM10/141DSP，不是整机PnR/FPS | ../HD720/MAP_MEASURED.json及res.csv |
| 引用既有硬件测量 | 2026-10-18 RISCV11 IN4报告55615XLR/243RAM10/145DSP；34秒19读数29.99–30.01fps；原BIT SHA0b7c2d11f0ee3ae176721b208d0d4934191479b80d708f803787c0234835e3f4 | evidence/hardware_*；rollback_RISCV11/SOURCE.json |
| 引用硬件组反馈 | V5 R14为0.85/0.95/0.85fps@320；切换<100ms仅监督/硬件组陈述，缺原始延迟事件采样 | evidence/hardware_feedback_*；不得写成本轮已测 |
| 编码计算 | 9384INT8weight+1632FP32affine+12INT32bias=15960B，11028参数；不是NPZ容器大小，也不是完整运输文件 | PARAMETER_BYTES.json |
| 混合实测/估算 | 720核心219RAM+历史外围93RAM估算312>256；30.523392GMAC/s需求>120lane@150MHz理想18G，原拓扑720p30 NO_GO。窄变体需GI/RTL，未训练验证 | ../HD720/FEASIBILITY.md；LATEST48已正式NO_GO，不再等待16:30 |

DP2已14:04:56完成：完整sc_engine含自主IN刷新、正式PE12/CFG6、D1 ROM+blob的32×24三风格9帧，6912输出像素与936IN系数逐项0LSB，CPU口实际加载4050blob记录、无复位切风格/背压/复位通过。结果与原始日志、源码/向量SHA清单已附evidence/DP2_*。它不证明原生640时序或板上性能。当前部署门已由LATEST48改为DP3 A/B分级，不能沿用47全面阻断。

尚未验证：屏幕网络FPS叠加的10分钟长稳、物理断电、当前板上版本与本地SHA直接绑定、完整风格切换端到端延迟、新候选实际板测。FPS叠加已有正式源码链证据，见FPS_OVERLAY.md；源码存在不能补齐长稳/屏幕实测。

尚未完成：TRACE全部场景最终艺术验收，尤其VG随物体组织的弯曲笔块/厚涂、UK有限平涂与语义色、ink中灰/自然笔意。D1的色相增量通过不等于这些最终目标通过。J1/J3/J4共享kernel候选仍须独立三风格回归裁决，无自动晋级。

loss下降、照片PSNR、原始未配准帧差不构成艺术通过。P0误归属图来自graphic_v6，P2/R42旧艺术裁决已作废。工具版本差异仅为观察事实，不证明它是DP1资源差异的唯一原因。


## 第48轮新增本轮实测与文件核验

| 证据类别 | 结果/边界 | 来源 |
|---|---|---|
|A原布局搜索|正式提交、本地含ignored文件及10ZIP目录无历史BIT绑定布局；恒等测试未运行、不可用。不是“恒等实测失败”|../DP3/BRAM_UPDATE.md、A_SEARCH.json、ARCHIVE_SEARCH.json|
|B候选整机PnR实测|56824XLR243RAM10145DSP，相对本地原版资源差0%；17setup/17hold全满足，最小+.240/+.026ns；434源仅6mem变化|../DP3/RESULT.json、FULL_BUILD.md及原始报告|
|候选本地BIT/HEX|生成成功并SHA归档，匹配D1 ROM/blob；无烧录、无新板测、尚未采纳|candidates/D1B60_B/MANIFEST.json、SOURCE.json|
|J4研究数值实测|INK/UK/VG三独立1000QAT全部train/export/eval/fidelity0；各18原生640三风格对J1盲页/key，各3style×1留出640golden0LSB|../QUEUE_R48_J4.json、../R48/REVIEW.md|
|J4实际审图|Codex未建议明确胜者；ink变化小、UK色更灰/描边重、VG增加交叉细纹，非沿物体弯曲笔触。CC独立盲评未到|../R44/J4_*/CODEX_VISUAL_NOTES.md|

工具版本差异未被证明是历史/本地资源差的唯一原因。B的时序通过不能替代新板上FPS；所有新位流标注未经板测。20:00监督裁决前，初稿含候选附件不等于选择新版。
