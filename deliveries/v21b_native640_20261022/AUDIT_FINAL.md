# 最终审计：限定范围内通过

审计时间：2026-10-22T18:35:50.538900+08:00。权威LATEST51第51轮17:15选择、顶部18:05更新；截止2026-10-22 19:30。交付网络D1B60_B_FWP1，原RISCV11整套回退。final=true仅表示交付选择与封包冻结，**不表示板测或完整艺术验收通过**。

| 检查 | 实际结果及范围 |
|---|---|
| 新版关键文件 | BIT d05ca9a2…、HEX e357099a…、固件6f932ae7…、blob84aeb3ba…逐文件匹配第51轮完整SHA；CRC20d4d7eb、48616B、4050记录、3风格匹配 |
| 原版回退 | BIT/HEX/固件/blob完整SHA及SOURCE.json所有条目匹配，CRC373deed7 |
| 原固件补丁 | 独立比较原/新13746B，恰好10字节、四指令，仅立即数位；两处LUI/ADDI实际还原CRC及取反前累积比较值；四lane输入重建补丁固件及零填充exact |
| 固件及ROM证据 | 六例原raw RV32日志、4050记录内容SHA与实际blob[16:]匹配；ROM_RESULT/ROM_READBACK/ALL_ROM_LOCALIZATION及候选/证据复制件一致；引用已有vendor逻辑回读，不是新板上读回 |
| 候选内部清单 | {"D1B60_B": 27, "D1B60_B_CRC": 35, "D1B60_B_FWP1": 33}；各目录除自身清单外所有文件尺寸/SHA与覆盖范围一致 |
| 全包MANIFEST | 覆盖包内每个文件，唯一例外为根MANIFEST.json自身以避免自引用；包含所有嵌套MANIFEST。生成后只读复核逐文件尺寸/SHA及精确文件集合，通过后才允许ZIP |
| 当前HTML | 20页、764个本地链接，目标全部存在且不逃出包；所有展示图和盲页均已包内化 |
| 当前决定文字 | 根目录说明、当前index、候选README/RESULT共17份扫描并人工复核；旧截止、等待选择及FWP1角色矛盾已清；旧B明确CRC_BLOCKED，GCC15/J1–J6不作部署 |
| 历史证据 | 367份MD/JSON/HTML快照哈希核验；history/pre51原字节保留。历史adopted=false、旧期限/失败/待监督状态是当时事实，不改写成当前结果 |
| 队列 | 已结束研究队列pid/queue_pid均null，未重启，未新训练或生成BIT；见evidence/FINAL_QUEUE_AUDIT.json |
| ZIP | sorted ZIP，包内根DELIVERY_20261022；生成后流式解压每个成员逐字节SHA/大小核对MANIFEST（MANIFEST自身使用实际哈希），精确检查文件集合及重复项；结果与ZIP SHA旁车在包外，避免自引用 |

没有把旧baseline-only脚本或会重写现用网络的draft verifier用于定稿。新只读验证器及封包脚本在source/，解压后可运行`python -X utf8 source/verify_final_package.py .`。全部SHA列于MANIFEST.json。

## 明确未审、未验证和未完成

- 本轮没有完整SoC启动仿真、实物板测、Flash独立回读、三风格各10分钟屏幕FPS录像、断电测试、新BIT版本绑定或完整切换原始事件采样。这些不是审计PASS的项目。
- 资源时序引用本地B已布线布局56824XLR/243RAM10/145DSP、17setup/17hold满足、最小+.240/+.026ns；FWP1未重跑PnR。历史55615及工具版本差异仅观察，不归结为唯一原因。
- DP2只为三风格合计9帧32×24/6912pixels/936coeff的功能仿真；不是VGA吞吐/板测。原raw RV32六例SPI/时间stub不等于相机/DDR启动。
- 历史RISCV11 29.99–30.01fps只引用原版约34秒串口证据，不转移到新位流。普通切换<100ms仅引用，无原始采样；完整双SPI/CRC含120ms idle不满足。
- 历史HTML1页（history/pre51及original_generated）保留当时字节，其旧相对链接不作为当前可打开入口验收。原始日志/源代码里的绝对工作路径是追溯字段，不承诺在解压目录可执行。
- 没有重新训练、重新评判全部历史盲页或重跑已有RTL/Unicorn/vendor测试；审计核验证据与当前交付字节绑定。原训练数据、全部优化器/checkpoint不是部署依赖，未作为完整复训环境交付。
- VG随形弯曲笔块/颜料块、UK纯色平涂、ink中灰与留白仍缺；720p30 NO_GO：核心map219RAM+历史外围估算93=312>256，30.523392G>理想18G，逐层lane下界208。
- 不上传、不合并、不烧录。本审计只认证清单、当前角色/声明及已有本地证据绑定，所有上述未验证事项保持未验证。
