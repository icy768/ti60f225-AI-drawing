# 实验事实与结论修正
- P0：已部署checkpoint按冻结合同重导出，npz/json逐字节一致，见P0/RESULT.json。保留事实。
- P1：CPU current/rotating IN诊断保留原始数值和图；constant组实现被LATEST44判为bug/不可靠，其失败不支持“冻结IN不可能”或“IN完全抹色”。现RTL无固件常数开关，不能宣称已支持。
- P2/R42：所有run完成状态、风格行隔离、梯度归因保留；正面和负面艺术比较结论全部INVALID_FIDELITY_R44。训练/评估前向未验证复现部署整数前向，不能用原来的灰淡基线作优劣裁决。
- 所有新候选导出在e1触发activation-scale mismatch，未改scale绕门、未采纳；这证明未满足合同，不证明容量或教师是唯一原因。
- 梯度归因：一张合法训练样本的obj_ab梯度集中layers.11（beta0.566、gamma0.103；其余层≤0.03），只支持局部假设。
- F0：正在对照常规FP32、合同冻结伪量化、现有hardware_qat整数STE前向；结果见../F0/FIDELITY.md。phase在v21脚本控制损失渐进而非直接改变前向，不能单凭phase0.332断言前向差异原因。
- R44仅研究线，F0未通过不启动；13:45后不启动新run；所有候选不进冻结部署包。

# P0基线图来源纠正
2026-10-22 12:00经SHA及validation.json交叉核验：
P0/BASELINE_01/integer_styles.jpg（489f9280…）来自delivery_pc_20261004/quantization，run=art_styles_c24_graphic_v6_cal100。它不是qat900_soft15现用v21b。原图原记录保留，禁止继续作现用基线。
实际v21b审计图SHA3c714251…，来源v21b_deploy_blob，validation.run=art_styles_c24_v21b_ukiyoe_qat900_soft15。二者不能互换。P0导出npz/json逐字节通过仍成立，与错误图来源分开。
LATEST44基于误归属图的“UK鲜艳而非褐黄”等视觉修正需要重新审核。不能擅自恢复P2/R42艺术比较结论；它们仍按指导作废。实际v21b三行图已重新审阅：UK偏米褐/深蓝、保留照片明暗与细纹，VG蓝黄调色强、笔触组织不足，ink缺中灰/有细噪点；不是完整场景艺术验收。
已恢复原错误montage的精确5张输入（前4张验证图+screen_photo_proxy），F0用部署v21b重新生成各图，并加camera，18组均原生640。合同冻结整数STE与独立golden 0LSB。普通FP32/普通QAT仍不满足≤2/255。
源检查点只保存完整模型sd/observer，不含optimizer/RNG；研究线使用新Adam显式记录。现有硬件报告与新候选验证完全分开。
证据见PROVENANCE_CORRECTION.json、RESULT.json、actual_v21b_integer_styles.jpg与部署源validation.json。

F0完整指定5输入+camera完成；接入r44_forward CPU/CUDA0LSB与有限梯度通过，baseline export npz/json逐字节不变。D1B60研究队列已启动，禁止自动采纳。
