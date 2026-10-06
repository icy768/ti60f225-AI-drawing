# C24/16 最终路线执行记录

## 固定部署图

主线保持 `C=24, Fc=16, n_res=4, block=dw1, norm=IN`，四种风格共享卷积主干，使用各自的 IN affine/系数 bank。训练侧新增的相机增强和时间一致性损失只改变权重，不增加推理算子，不改变现有 13 层 RTL 接口。

## 已落实的训练侧修改

- `algo/train.py` 增加固定随机种子 `--seed`；
- `--camera_aug_prob`：模拟曝光、通道增益、gamma 和小幅传感器量化噪声；
- `--temporal_weight/--temporal_shift`：对合成相邻帧做有效重叠区域的一致性损失；推理不携带光流、循环状态或额外缓存；
- `--weights_only`：从已验证 checkpoint 开启独立的低学习率微调，避免错误恢复旧 OneCycle 调度；
- 部署目录 `runs/c24_dw1_in` 和 `runs/c24_gram` 增加结构保护，防止误用 C28、dw2、BN 等不兼容配置；
- `workers=0` 时关闭 `persistent_workers`，训练入口可在单进程环境运行；
- `algo/final_route_config.json` 和 `tools/run_final_route.ps1` 固化实验参数和输出目录。

## 正式实验

```powershell
cd C:\Users\蔡哲涵\Desktop\fpga\FPGAProjects\StyleCam
tools\run_final_route.ps1 -Iters 3000
tools\run_final_route.ps1 -Iters 3000 -QAT
```

两条实验分别输出到 `runs/final_route_camera_temporal` 和 `runs/final_route_camera_temporal_qat`。它们都是质量候选，不能直接覆盖 `rtl/gen` 或 `sw` 的部署文件。

## 接受门槛

候选只有同时满足以下条件才可生成新的 RTL：

1. 与当前 checkpoint 使用相同验证图、同一教师、同一 PSNR/SSIM 协议；
2. 至少两种命名艺术风格在连续视频中保持风格可辨识，运动和曝光变化下无明显闪烁；
3. 按 StyleCam 实际整数舍入、饱和和 IN bank 刷新合同完成软件整数对拍；
4. Efinity 完整工程综合、时序和资源通过；
5. Ti60 上 640×480 输入前端稳定 30 fps，风格化输出达到至少 15 个不同 `frame_id`/s，连续运行无丢帧/underflow；
6. 至少两种风格帧边界切换小于 100 ms，并记录切换期间的 frame_id。

当前报告中的 150 MHz/26.5 fps 是网络核估算，不是整机验收；`vision_core.v` 的 `a_latest` 策略可能覆盖输入中间帧，必须由硬件组增加或记录相机、NN、显示三类帧计数。
