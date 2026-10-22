# 当前权威核实 2026-10-22T17:09:05.188665+08:00：LATEST50；138–141已处理，FWP1待20:00监督选择

截止23:30；19:00不新run、20:00不编译/生成BIT，21–23定稿。OWNERcodex、CC监督，无交付前板测/烧录/外发/上传合并/子代理，不停健康任务。

138 FWP1：原RISCV11固件13746B，未重编译。CRC用于加载比较（取反累积值）与启动日志，两对LUI/ADDI共四指令10字节立即数位变化，其他字节/分支/地址不变；超过预计≤8B但未越常量编码，需监督明确接受实测范围。原raw RV32六例PASS、D1实际4050写逐字exact。vendor更新本地B布局CPU ROM；18逻辑初始化存储器只有CPU32bit变化，显示/INROM14项exact；四lane读回重构补丁固件exact，重复更新/恢复旧ROMpayloadexact。不是历史A级全SHA恒等，不是板上物理读回或完整启动。BIT SHAd05ca9a28994af523131805a1e427a622ce8dcedba1b386bb023052dbdd74475，HEXe357099aa9e3930b558ca453f71d367a279dae8d4909f6febfb181816af6ddd6，固件SHA6f932ae7dc75ebead8fff869289b41b5dc55c0ff147130188f3f133d2a094408。资源时序引用B，未新PnR。DP3/FW_PATCH/RESULT.md。

139 拒绝CRC补偿；D1blob字节和CRC20d4d7eb不改，不伪装373deed7。BLOB_LOAD.md已记。

140 可选J6_UK已17:04:16正常完成1000QAT/train/export/eval/fidelity全0；独立J1_60完整sd/新Adam、共享kernel+affine/phase1/observeroff/尺度锁死。原三张v21 UK画作SHA核验取10主色，新增可微软调色板项最终初始loss30%，weight64.82757568，复算.3000000056；父本obj_ab4.269344不变。18组native640三风格整数盲页直接对D1B60，另3style×1留出640golden0LSB。Codex已看三contact及UK原像素裁片：更平但棕灰/压暗，无稳健胜出，不推荐晋级，不启部署链，不追加。CC待独立复核；J5 CC50采用Codex无胜者，不称另复看。

141 旧B研究附件/不可启动；GCC15整份重编译修复备选保留风险；FWP1首选候选未采纳，FINAL_DECISION.md已留20点模板，selected_network=null/finalfalse。原RISCV11回退完整保留。720pNO_GO；原生640屏幕FPS源码证据、历史FPS引用/当前10min断电切换未验、DP2小图范围、艺术缺口均保持。

额度RPC认证失败，5h/周未知非耗尽。当前无活动项目队列，不重启旧PID。20点明确选择后才改baseline-only finalize脚本，23:30如实交付再停自动任务。下面仅历史。

---
