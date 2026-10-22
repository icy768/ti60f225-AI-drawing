# F0 CPU 保真度

{
  "fp32": {
    "mae_255_mean": 14.743608519000775,
    "worst_case_mae_255": 20.598716362847224,
    "pass_all_mae_le2": false
  },
  "qat_phase1_frozen": {
    "mae_255_mean": 2.9524139781057097,
    "worst_case_mae_255": 4.227220052083333,
    "pass_all_mae_le2": false
  },
  "hardware_qat_frozen": {
    "mae_255_mean": 0.0,
    "worst_case_mae_255": 0.0,
    "pass_all_mae_le2": true
  }
}

纯FP32/常规round伪量化不实现19位acc右移、18位M/20位B饱和及逐帧整数统计，因此须按逐层证据定位。现有hardware_qat的hard路径显式实现这些整数步骤，soft路径仅提供STE梯度；单独报告，不能把常规QAT结果改名为PASS。

phase在v21脚本只影响loss权重；observer重新标定可造成候选e1尺度不一致，但不是所有颜色偏差的唯一原因。原始checkpoint的observer值在本轮未改变。

输入：要求montage的五张精确保留原始输入及一张camera，每个样本3风格，原生640。重要来源纠正：P0原montage属于graphic_v6_cal100，不属于现用v21b；本轮用相同原输入重新跑部署v21b。RESULT.json包含输入SHA、MAE/PSNR/逐层范围。

## 逐样本MAE/PSNR（255域，PSNR无限时以∞记）

|输入|风格|FP32 MAE / PSNR|普通QAT MAE / PSNR|整数STE MAE / PSNR|
|---|---|---|---|---|
|0|van_gogh|12.427868 / 24.234dB|3.431696 / 34.560dB|0.000000 / ∞|
|0|ukiyo_e|9.826176 / 26.041dB|2.116386 / 38.611dB|0.000000 / ∞|
|0|ink_landscape|14.034151 / 23.670dB|2.652454 / 36.752dB|0.000000 / ∞|
|1|van_gogh|19.349410 / 20.482dB|3.360266 / 34.911dB|0.000000 / ∞|
|1|ukiyo_e|15.547637 / 22.246dB|2.407196 / 37.433dB|0.000000 / ∞|
|1|ink_landscape|17.488979 / 21.777dB|2.640916 / 36.263dB|0.000000 / ∞|
|2|van_gogh|17.414745 / 21.375dB|3.216732 / 35.228dB|0.000000 / ∞|
|2|ukiyo_e|11.976122 / 24.305dB|2.127670 / 38.557dB|0.000000 / ∞|
|2|ink_landscape|14.327154 / 23.299dB|2.648148 / 36.399dB|0.000000 / ∞|
|3|van_gogh|15.666360 / 22.210dB|4.227220 / 32.675dB|0.000000 / ∞|
|3|ukiyo_e|10.955571 / 24.701dB|2.733703 / 36.011dB|0.000000 / ∞|
|3|ink_landscape|15.522457 / 22.722dB|3.301627 / 34.588dB|0.000000 / ∞|
|4|van_gogh|14.167706 / 23.238dB|3.392288 / 34.756dB|0.000000 / ∞|
|4|ukiyo_e|9.377400 / 26.362dB|2.518821 / 37.051dB|0.000000 / ∞|
|4|ink_landscape|13.550812 / 23.807dB|2.956853 / 35.626dB|0.000000 / ∞|
|5|van_gogh|20.598716 / 20.272dB|3.874506 / 33.364dB|0.000000 / ∞|
|5|ukiyo_e|14.090196 / 22.925dB|2.731713 / 36.305dB|0.000000 / ∞|
|5|ink_landscape|19.063494 / 20.914dB|2.805256 / 35.056dB|0.000000 / ∞|

## 层间偏差定位

样本0 VG在相同合同尺度下，普通QAT的层MAE（量化单位）从e1的0.0043累积到d1b的1.5504及d2的3.4317。观察到的范围均约0..255，但数值仍偏离；仅冻结observer和phase=1不足以复现整数舍入/IN统计/系数饱和。未做逐因素消融，不能把所有偏差归于其中单一因素。

|模式|层|平均层MAE（18样本）|最大激活/scale|
|---|---|---|---|
|fp32|e1|0.197049|641.453|
|fp32|e2|0.402364|890.340|
|fp32|r0a|0.886301|704.785|
|fp32|r0d|0.937514|758.255|
|fp32|r1a|0.990256|781.989|
|fp32|r1d|1.077441|651.275|
|fp32|r2a|1.111810|1163.546|
|fp32|r2d|1.507659|628.763|
|fp32|r3a|0.828082|934.110|
|fp32|r3d|1.218098|518.860|
|fp32|d1a|1.063220|1556.542|
|fp32|d1b|6.379697|808.400|
|fp32|d2|14.745390|255.000|
|qat_phase1_frozen|e1|0.002922|255.000|
|qat_phase1_frozen|e2|0.016364|255.000|
|qat_phase1_frozen|r0a|0.051041|255.000|
|qat_phase1_frozen|r0d|0.087681|255.000|
|qat_phase1_frozen|r1a|0.180736|255.000|
|qat_phase1_frozen|r1d|0.216430|255.000|
|qat_phase1_frozen|r2a|0.339245|255.000|
|qat_phase1_frozen|r2d|0.488236|255.000|
|qat_phase1_frozen|r3a|0.303906|255.000|
|qat_phase1_frozen|r3d|0.456896|255.000|
|qat_phase1_frozen|d1a|0.454418|255.000|
|qat_phase1_frozen|d1b|1.445005|255.000|
|qat_phase1_frozen|d2|2.952415|255.000|

完整来源纠正见PROVENANCE_CORRECTION.md。原始checkpoint的args指向train_art_quant_distill硬件整数STE训练（qat900_soft15），常规v21训练forward不是原QAT硬前向。本轮修正接入的是已有hardware_qat，不是给golden结果换名；r44_forward统一供训练/评估调用并有独立CPU/CUDA预检。

基线npz/json逐字节验证：PREFLIGHT.json PASS。源没有opt/RNG，完整模型状态继续，新Adam明确记录。当前R44首次1000QAT步是有限研究规格，不能与R42的3000FP32+1000QAT直接当成等价实验强度。
## 数据边界
当前恢复的v21b原训练域为data/val2017按文件名切分4800 train/200 heldout（这是该旧分支数据划分，不是T-A3的1171/92）。本轮4张普通montage输入全部属于200 heldout，不在4800优化集，二者交集0；screen proxy和camera仅推理。使用v21b自己的原配方数据恢复，未用heldout调参。

当前额度只读工具返回需账号认证，当前rollout额度字段primary/secondary=null，无法核实精确5h/周百分比；没有额度耗尽证据，不停止健康后台，也不重复旧摘要24%/61%。F0/QUOTA_CURRENT.json保留原失败原因。
