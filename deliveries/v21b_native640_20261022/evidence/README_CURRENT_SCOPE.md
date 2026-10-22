# 证据阅读范围

当前选择以包根FINAL_DECISION.md为准：LATEST51于17:15选择D1B60_B_FWP1，18:05将截止提前为19:30。旧B因CRC拒绝不能部署，GCC15修复未选中，原RISCV11整套回退。

本目录保存测试当时的报告、日志、源码和监督原文。旧期限、待监督、adopted=false、基线复现失败等是当时事实；它们不表示最终选择仍待定，也不改变各测试原有范围。部分报告先失败后修复，完整过程保留。原始数据没有改写；逐文件SHA在根MANIFEST.json。

FWP1未进行完整SoC启动或新板测；vendor逻辑ROM读回不等于实物Flash回读。DP2仅三风格合计9帧32×24功能测试。历史FPS仅属于原RISCV11。完整限制参见根STATUS_AND_LIMITS.md和AUDIT_FINAL.md。
