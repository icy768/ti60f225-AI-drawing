> LATEST50：原固件常量补丁FWP1验证完成，首选候选candidates/D1B60_B_FWP1，BITd05ca9a28994…，仍待20:00监督选择；未完整启动/板测/采纳。GCC15修复仅备选（整份重编译风险）；旧B616e40bb…+D1明确CRC_BLOCKED/研究附件不可启动。原RISCV11回退保留。见evidence/FW_PATCH_RESULT.md与FINAL_DECISION.md。

> LATEST49：旧D1B60_B位流616e40bb…配D1blob会被原固件CRC拒绝，启动BLOCKED。独立CRC修复候选见candidates/D1B60_B_CRC，BIT3f302996…/HEX8fc0a9be…，本地交叉编译+RV32加载器+ROM更新验证，尚未完整启动/板测/采纳；20:00监督选择未定。原RISCV11回退保留。详见evidence/DP3_BLOB_LOAD.md。

# 新版网络候选 D1B60（LATEST48，尚未采纳）

原生640×480。原kernel保持，VG gamma/beta ROM改270字，UK/ink/epsilon不变。新ROM必须进入位流，单换启动blob会被自主IN刷新覆盖。原版仍保留为回退；20:00由监督按证据选择交付网络。

| 证据 | 结果与边界 |
|---|---|
|艺术增量|CC47/48通过VG色相增量，纹理变柔；弯曲笔触、颜料块完整目标未达|
|HG1整数视频|16val+camera30 raw/warp相对原版0.803714/0.795645；不是板测|
|DP2完整自主IN引擎|三风格合计9帧32×24，6912像素/936IN系数0LSB，CPU口4050记录加载、无复位切换/背压/复位PASS；不是原生640时序|
|DP3 A|未找到与历史BIT绑定的原布局；恒等测试未执行，A级不可用，见../DP3/BRAM_UPDATE.md|
|DP3 B|独立整机interface/map/PnR已完成：B_PASS_UNTESTED_ON_BOARD。对本地原版56824/243/145、setup+.240/hold+.026；XLR差≤1%、RAM/DSP相同、全部时序满足才能通过，见../DP3/FULL_BUILD.md|
|历史/本地工具|2026.1.132.4.5/2026.1.132；原版本地XLR比历史55615多2.1739%。原因未唯一归因|

**所有新位流未经板测，当前没有D1采纳或新板上FPS结论。** 原版BIT/HEX/固件/blob与SOURCE/SHA在rollback_RISCV11。FPS屏幕网络发布IRQ→OSD链见FPS_OVERLAY.md；引用历史29.99–30.01fps，当前10分钟屏幕长稳/断电/新版本绑定未测；切换<100ms缺原始采样。

---
# v21b 原生640交付初稿
生成 2026-10-22T11:58:12.494359+08:00；最终截止2026-10-22 23:30，当前不是最终验收包。
现用v21b为已板测回退基线；D1B60为LATEST48新版候选，20:00监督按DP3证据决定。所有新位流未经板测，当前尚未采纳。

| 文件 | SHA256 |
|---|---|
| baseline/qparams.json | b3760512b460306f3c3cff8b0dec879625d3a53d2b32500293408ab8833d98a0 |
| baseline/qparams.npz | 32dfc6c4d0d639c9f46275fa307c5d1d5fcf71771c0d99a06f08fb2182067848 |
| baseline/student.pt | d0d19437fa91a8424a38baddc2f03d2bbf79bb6a93da94342fb8bef97fd907eb |

已有硬件证据：evidence/hardware_README.md（RISCV11 IN4，2026-10-18），55615/60800 XLR、243/256 RAM10、145/160 DSP，setup +0.253ns、hold +0.026ns。19个板内读数覆盖34秒，29.99–30.01fps。该记录不是本轮板测；板上模型CRC373deed7与本地qparams SHA的直接绑定仍需原始包核验。

| 题目指标 | 状态与依据 |
|---|---|
|640×480@30fps输入、原生640输出≥15fps|已有硬件组报告30fps；本轮无新测量|
|风格切换<100ms|LATEST44转述已有硬件组结论；原始延迟采样日志尚未收录，不作本轮实测|
|三风格学习参数<500000B|11028参数（参数数不等于字节数）；存储逐字段计数15960B（声明编码的计算值）；完整blob实测48616B，见PARAMETER_BYTES.json|
|三风格结构差异|视觉上有差别但完整TRACE底线未通过，见GAPS.md|

打开 index.html 查看证据。没有执行烧录、Git上传或合并。原版回退位流沿用硬件组既有包；新候选位流按DP3门核验，不把旧板测记为新版本测量。

来源纠正：旧integer_styles.jpg不是现用v21b，见evidence/PROVENANCE_CORRECTION.md。真实图为evidence/actual_v21b_integer_styles.jpg。参数编码计数15960B，完整运输blob 48616B，blob SHA 9a1b2382e2c9953f775f5c9c7e5b06fd93e5cad9bcdffa8086dbbe41541a5d5b。

完整blob头STN1、4050条写入与原cfg.txt逐字一致；其CRC32实算373deed7，与硬件README历史启动CRC相符。该一致性不是新Flash回读或板上内存SHA验证，见DRAFT_VERIFICATION.json。
