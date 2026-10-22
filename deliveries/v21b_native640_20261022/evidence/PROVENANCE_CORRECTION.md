# P0基线图来源纠正
2026-10-22 12:00经SHA及validation.json交叉核验：
P0/BASELINE_01/integer_styles.jpg（489f9280…）来自delivery_pc_20261004/quantization，run=art_styles_c24_graphic_v6_cal100。它不是qat900_soft15现用v21b。原图原记录保留，禁止继续作现用基线。
实际v21b审计图SHA3c714251…，来源v21b_deploy_blob，validation.run=art_styles_c24_v21b_ukiyoe_qat900_soft15。二者不能互换。P0导出npz/json逐字节通过仍成立，与错误图来源分开。
LATEST44基于误归属图的“UK鲜艳而非褐黄”等视觉修正需要重新审核。不能擅自恢复P2/R42艺术比较结论；它们仍按指导作废。实际v21b三行图已重新审阅：UK偏米褐/深蓝、保留照片明暗与细纹，VG蓝黄调色强、笔触组织不足，ink缺中灰/有细噪点；不是完整场景艺术验收。
已恢复原错误montage的精确5张输入（前4张验证图+screen_photo_proxy），F0用部署v21b重新生成各图，并加camera，18组均原生640。合同冻结整数STE与独立golden 0LSB。普通FP32/普通QAT仍不满足≤2/255。
源检查点只保存完整模型sd/observer，不含optimizer/RNG；研究线使用新Adam显式记录。现有硬件报告与新候选验证完全分开。
证据见PROVENANCE_CORRECTION.json、RESULT.json、actual_v21b_integer_styles.jpg与部署源validation.json。
