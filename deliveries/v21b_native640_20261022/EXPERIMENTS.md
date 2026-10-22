# 实验结论及来源纠正

P0旧montage实际graphic_v6_cal100，不是现用v21b；原图与SHA追溯见evidence/PROVENANCE_CORRECTION.md，真实图actual_v21b_integer_styles.jpg。P2/R42正负艺术比较全部作废，完成、隔离和有限梯度归因事实保留；constant-IN诊断不可靠，不推唯一原因。

F0完成18组原生640，hardware_qat整数STE与独立golden逐像素0LSB，冻结基线npz/json字节一致；普通FP32/普通QAT未满足≤2/255。新研究run统一r44_forward/phase1/observeroff/原激活尺度锁定，新Adam明确非优化器恢复，val只推理不优化。

R44 D1B60为唯一确认艺术增量（VG本色），D2/D3无艺术胜出；J1–J6没有最终替换D1。J6单UK新项参考10色软量化，初始loss30%校准，虽更平但棕灰/压暗，监督51采用Codex不晋级结论；不称独立全量复看。完整盲页在research/R44，各run数据是历史事实，不代表全部艺术通过。

部署依次通过D1 ROMdiff、HG1、DP2小图自主IN、B完整布局比较；原固件CRC阻断被查明，FWP1以原二进制仅常量修改解决本地加载链。最终采用由LATEST51明确授权。没有新板测/完整SoC启动，不从loss或照片PSNR推艺术通过。
