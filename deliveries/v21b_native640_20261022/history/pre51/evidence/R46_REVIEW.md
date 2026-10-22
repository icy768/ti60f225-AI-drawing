# R46 校准实验结案（Codex目视，不冒充CC盲评）

D2B60_CAL_R1与D3B60_CAL_R1都1000QAT正常结束，phase1、observer off、原合同scales锁死，仅对应仿射改变；训练/export/eval rc均0。首个目标风格初始loss项比例.60校准得到ink42.5623588562、UK85.7930374146；不是直接系数.6，也不是三风格合计loss的60%。原D2B60_CAL在150步无记录退出，原因未知，现场保留于R45_CAL/INTERRUPTION_01；R1从原部署ck新Adam开始，不伪称恢复checkpoint。

R46_RECOVERY/CANDIDATE_FIDELITY.json：每个新ck各三风格、同一原生640留出输入，与独立冻结导出golden逐像素0LSB，共6case。R44/{ID}/RESULT.json保存六输入×三风格，非目标风格逐像素不变。数值门通过不代表艺术通过。

实际打开两项原生input0/input1，以及ink六输入contact、UK后三输入contact。已读key，不记为独立盲票。ink中灰增加但树林/人物背景整体灰填充、对比丢失，camera面部和暗部变灰照片；食物仍有蚀刻点/轮廓，无有组织皴擦收益。UK平坦区域变大但大面积暗蓝灰、红衣/肤色过暗、边线和细节弱化；camera墙/人形接近同色块，色纯与清晰主体未达。

Codex判ART_FAIL，不晋级、不追加无依据训练、不合并D1B60。不把该结果归因为容量/教师/IN唯一因素；监督可独立复核现有盲页。新变量等14:00后最新明确监督。

D0对D1B60的六输入同强度直接盲页新增R44/D0_D1B60/index.html，key单独保存，供检查obj_ab增量；一对run不能证明唯一因果机制。D1B60扩大目视记录EXPANDED_VISUAL_NOTES.md保留色相收益与纹理变柔代价；仍待监督且ROM部署阻断未解除。
