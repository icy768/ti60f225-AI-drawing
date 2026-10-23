# 最终交付决定：D1B60_B_FWP1

final: **true**。权威：Claude LATEST第51轮，2026-10-22 17:15；原定20:00的选择已提前完成。截止2026-10-22 19:30 Asia/Shanghai（第51轮顶部18:05更新覆盖旧节点）。本文件记录交付选择，不表示完整艺术验收或新板测通过。

监督原文：“交付网络（新版）D1B60_B_FWP1”；“FWP1：PASS，作为首选修复件”；“研究线到此全部结束”。完整原文见evidence/guidance_LATEST.md。

| 角色 | 文件与证据 | 限制 |
|---|---|---|
| 交付网络 | candidates/D1B60_B_FWP1；下表完整SHA；blob CRC20d4d7eb | 未经板测，未完整SoC启动仿真；新BIT屏幕FPS未实测 |
| 回退 | rollback_RISCV11；原BIT0b7c2d11…/blob9a1b2382…，CRC373deed7 | 历史29.99–30.01fps串口测量引用，约34秒；非本轮测量 |
| 研究附件 | GCC15修复件3f302996…、原B616e40bb…（CRC_BLOCKED，不可启动）、J1–J6、720p研究 | 不作为部署组合使用；J4/5/6均无明确胜者 |

| 新版文件（candidates/D1B60_B_FWP1/） | SHA256 |
|---|---|
| D1B60_B_FWP1_UNTESTED.bit | d05ca9a28994af523131805a1e427a622ce8dcedba1b386bb023052dbdd74475 |
| D1B60_B_FWP1_UNTESTED.hex | e357099aa9e3930b558ca453f71d367a279dae8d4909f6febfb181816af6ddd6 |
| stylecam.bin | 6f932ae7dc75ebead8fff869289b41b5dc55c0ff147130188f3f133d2a094408 |
| net_blob.bin | 84aeb3bae88b4c883a5ff8c8111b289f129359cb82d89df49219a743f14587bd |

原RISCV11回退BIT SHA0b7c2d11f0ee3ae176721b208d0d4934191479b80d708f803787c0234835e3f4；HEX SHAcabfc39c999af9f6450d46c5ae3c31cd318b7c9701874d29a187f7d1d73ea826；固件SHA2319ab969c16850d6fbc750c771cbcfc3d03cd1b76299942e6fb6334c0ecaaca；blob SHA9a1b2382e2c9953f775f5c9c7e5b06fd93e5cad9bcdffa8086dbbe41541a5d5b。回退必须整套配置与blob配对。

接受10字节/4条指令：同一个CRC有两处语义用途——启动日志模型标识和加载器内部取反前累积值。每处LUI/ADDI，只改立即数位；没有改分支、地址、寄存器或其余固件字节。比预计≤8字节多2字节，监督第51轮明确接受；日志标识同步更新，不伪装原模型。无重新编译。

证据：VG物体本色艺术增量（监督5/6及16张扩大验证），HG1 raw/warp=.803714/.795645；DP2含自主IN完整引擎小图3风格合计9帧32×24/6912像素/936系数0LSB；B布局本地56824XLR/243RAM10/145DSP、17组setup/hold满足，最小+.240/+.026ns；FWP1原raw RV32六例PASS、4050记录exact，18逻辑ROM仅CPU32bit变化及往返通过。

最终限制：新BIT资源时序引用原B布局，未新PnR；本地与历史工具版本不同，XLR比历史55615多2.1739%，未证明唯一原因。没有新板测、屏幕三风格各10min/断电/当前版本Flash回读/完整切换原始采样；没有完整SoC启动。VG弯曲笔块、UK纯色平涂、ink中灰留白目标仍缺；720p30 NO_GO。交付选择不等于上述项目达标。

交付前未烧录、未上传、未合并；后续验证参见POST_DELIVERY_TEST.md。
