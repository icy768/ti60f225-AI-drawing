# 三风格原生640最终交付包

**交付网络：D1B60_B_FWP1；回退：原RISCV11；附件：其他研究产物。** 监督第51轮于2026-10-22 17:15明确选择，研究结束。18:05更新：19:05审计、19:15 ZIP及SHA、19:30交付。新版未经板测/完整SoC启动仿真；最终艺术目标仍有缺口。打开index.html、FINAL_DECISION.md和MANIFEST.json。

新版文件全部在candidates/D1B60_B_FWP1/，BIT/HEX/原固件常量补丁/blob必须配套，CRC20d4d7eb。回退使用rollback_RISCV11/原配置及原blob，CRC373deed7。烧录、独立回读、三风格10min、切换、断电及回退操作规格见POST_DELIVERY_TEST.md；本轮没有执行。GCC15修复仅研究附件；旧B616e40bb…+D1被原固件拒绝，不可启动。

| 赛题要求 | 当前状态 |
|---|---|
| 640×480@30输入、原生640输出 | 沿用正式RISCV11接口/拓扑；新板上绑定未测 |
| 风格化输出稳定≥15fps | 原RISCV11历史串口29.99–30.01fps；新版未测，不能据PnR推断 |
| 屏幕网络FPS叠加 | IRQ发布计数→固件→OSD源码链存在；当前屏幕录像未收录 |
| 风格切换<100ms | 已有硬件组结论仅引用，原始采样未收录；完整两次SPI/CRC重载现120ms idle不满足，不能替代普通风格切换证据 |
| 三风格参数<500000B | 声明编码计算15960B（INT8 weight9384+FP32 affine6528+INT32 bias48）；实际完整blob48616B；不是板内独立测量 |
| 三风格结构差异 | 部分；完整TRACE艺术底线未通过，见GAPS.md |
| 1280×720@30高阶挑战 | NO_GO：核心mapRAM219+历史外围估算93=312>256；30.523392GMAC/s>120lane@150MHz理想18G；逐层lane下界208，窄GI/RTL未验证 |


新版VG物体本色增量通过，HG1=.803714/.795645；纹理变柔、弯曲笔触与颜料块仍缺。DP2仅32×24合计9帧功能仿真0LSB，不能扩称VGA时序或板测。原固件13746B只改4条立即数共10B；本地B布局56824/243/145、+.240/+.026ns，新ROM更新引用此资源时序，未新PnR。历史55615和工具版本差异仅观察，非唯一因果结论。

| 新版文件 | SHA256 |
|---|---|
| D1B60_B_FWP1_UNTESTED.bit | d05ca9a28994af523131805a1e427a622ce8dcedba1b386bb023052dbdd74475 |
| D1B60_B_FWP1_UNTESTED.hex | e357099aa9e3930b558ca453f71d367a279dae8d4909f6febfb181816af6ddd6 |
| stylecam.bin | 6f932ae7dc75ebead8fff869289b41b5dc55c0ff147130188f3f133d2a094408 |
| net_blob.bin | 84aeb3bae88b4c883a5ff8c8111b289f129359cb82d89df49219a743f14587bd |

history/和HISTORICAL_EVIDENCE.json保存决定前的不可变快照；evidence/、research/中的历史未采纳/旧时间字段仅表示当时状态，当前交付选择以FINAL_DECISION.md为准。所有网页图像和研究盲页均在包内，原训练数据/全部checkpoint不属于交付部署依赖。

本地验证、引用板测、估算、未验证和未完成分列于STATUS_AND_LIMITS.md。包外ZIP SHA旁车不放进自引用清单。没有上传、合并、烧录。
