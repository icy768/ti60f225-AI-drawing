# R44 接入约定
train_art_styles_r44.py基于v21配方另存，不改历史脚本。所有学生/teacher/temporal前向经r44_forward.TinyStyleNet→hardware_qat.forward，phase固定1，QCfg.enabled=True/observe=False。逐次检查全部合同尺度，绝不重校准或覆写scale。
从部署student.pt完整sd（含gamma/beta、kernel、observer buffer）开始。源checkpoint仅含cfg/styles/sd/qat/it/args，无optimizer和RNG；无法声称恢复不存在的状态。使用新Adam并显式记录optimizer_restored=False，旧实验没有作为初始化。新候选须冻结导出，e1或任一尺度不符立即失败。
这只是研究接入，不改变交付网络。部署checkpoint的qt900原训练已使用hardware_qat，R42改用常规forward是重要差异；不能将损失phase直接当作前向插值系数。
