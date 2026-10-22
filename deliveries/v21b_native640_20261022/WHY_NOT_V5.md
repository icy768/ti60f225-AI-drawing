# 为什么比赛交付不用V5

依据包内evidence/guidance_PLAN.md v7.0及evidence/hardware_feedback_NETWORK_COMPARISON_20261019.md。本次交付选择由LATEST51确定为D1B60_B_FWP1，原RISCV11提供回退；保护V5原档案。

硬件组R13/R14报告及表图已收录evidence/。这是引用的硬件反馈，未在本轮重新板测。报告区分R13完整V5约56,835XLR/182RAM/132DSP、0.65–0.75fps；R14反馈约0.85–0.95fps。原始表图的风格稳态范围为VG约0.70–0.85、UK0.75–0.95、ink0.65–0.85fps，R14处理时间约1127.42/1059.00/1147.27ms。监督摘要0.85/0.95/0.85是范围高端，不能称长期平均；均未达15fps。摄像头30fps和HDMI刷新率不能充当网络输出FPS。

32路方案64,269XLR超过60,800，64路DSP超限；不能称所有V5实现都无法装入，也不能把现有访存效率归为Ti60性能上限。更大并行度需要重新设计和验证。

原RISCV11历史资源55615/60800XLR、243/256RAM10、145/160DSP；本地B布局56824/243/145。二者来源与工具版本不同，不混用。FWP1引用本地B布局时序，新版板FPS未测。

真实v21b原生640整数基线是evidence/actual_v21b_integer_styles.jpg。旧evidence/integer_styles.jpg属于graphic_v6_cal100，误归属已纠正，不能再用它支持v21b艺术结论；见evidence/PROVENANCE_CORRECTION.md。硬件组离线对照图身份以原图标题和报告为准，不能冒称同像素板上结果。最终艺术缺口见GAPS.md。
