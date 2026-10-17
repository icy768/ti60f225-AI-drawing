# 独立三风格网络首版（2026-10-17）

共享浅层内容特征，三个独立多尺度空间专家与输出头：vangogh、ukiyoe、ink。固定权重为本任务新建网络，推理无NPR后处理。

- [七类输入/三风格实际对比](deployment_refine6000/preview_7_categories.jpg)
- [17场景FLOAT原尺寸](deployment_refine6000/float_native_size/comparison.jpg)
- [17场景Q31整数](deployment_refine6000/normative_integer_comparison.jpg)
- [逐场景图片和视频HTML](release/INDEX.html)（下载本目录后用浏览器打开）
- [网络结构](claude_impl/model.py)、[训练实现](continuation_impl/train_art.py)
- [DDR3计算/带宽/存储数据](deployment_refine6000/hardware/HARDWARE_FINAL.md)
- [固定整数格式](reports/continuation/INTEGER_INTERFACE.md)

## 推理

Python3.10；依赖版本见requirements.txt。以本目录为工作目录：

```bash
python continuation_impl/infer.py --model deployment_refine6000/tristyle_v3_fp32.pt --input data/test/water_day.png --output output/float --style all
python continuation_impl/infer.py --backend int8 --model deployment_refine6000/tristyle_v3_int8.ts --input data/test/water_day.png --output output/int8 --style all
python continuation_impl/infer.py --backend integer-reference --model deployment_refine6000/tristyle_v3_hw.bin --input data/test/water_day.png --output output/integer --style all --size 320 240
```

风格可选vangogh/ukiyoe/ink/all；默认原尺寸，复制边缘补齐8倍数后裁回；--size显式改变分辨率。FLOAT、fake-INT8和整数对照来自同一600步保持型QAT权重。Q31与oneDNN舍入约定存在差异，分别保留输出。

## 文件

完整固定格式部署包tristyle_v3_hw.bin为495552B，已包含共享与三专家、偏置、Q31常量、图描述、头与对齐。tristyle_v3_all.bin是替代JSON格式，不需一起部署。主机FLOAT权重.pt、oneDNN INT8.ts及fake量化状态均保留。

视频video/为同源640–789帧、每面板320×240；video_full640/为760–789帧、每面板640×480。均为Sintel源动画的主机离线推理，不是FPGA实时录屏。源片Blender Foundation CC BY3.0，原始来源及许可页在sources/Sintel_license.html。不同后端量化数据在final_numeric_verification.json；包分项在tristyle_v3_hw.bytes.json。

训练目标、种子与权重参数见runs/continuation_final_refine/config.json；源代码快照保留。训练照片、教师二进制、目标缓存和优化器历史不随仓库上传，来源与实际成员哈希在data/USED_DATA_manifest.json。可用continuation_impl/restore_recorded_inputs.py恢复已记录输入，再生成内容/深度/目标缓存；继续训练须使用新run名，不覆盖交付权重。CUDA训练不保证位精确重放。

第三方代码许可保留在external/与sources/；历史艺术参考的来源在sources/met_*.json。板卡为Ti60F225I3-V4、DDR3 x16/256MiB，详细事实见HARDWARE_INPUT.md。硬件成本是参数化估算；尚无整网Efinity综合或上板帧率数据，算术RTL单元仿真范围见rtl_math/README.md。
