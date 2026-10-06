# C24/16 共享主线：route_v2 训练执行说明

本路线保留 C24=24、Fc=16、4 个 dw1 残差块、IN、PixelShuffle 和现有 13 层 RTL 图。默认不覆盖 `runs/c24_gram`、`runs/c24_dw1_in` 或 `rtl/gen`。

## 已实现的训练侧能力

- `algo/train.py` 新增 `--camera_aug_prob`：只在训练时加入低幅曝光、白平衡、gamma 和传感器噪声变化；推理图不增加算子。
- 新增 `--temporal_weight` 与 `--temporal_shift`：用小平移合成相邻帧，按有效重叠区域计算对齐后的输出一致性损失；推理不使用光流、循环状态或额外 FPGA 算子。
- 新增 `--weights_only`：只载入旧检查点的网络权重和激活量程，重置 Adam/OneCycle，支持独立的低学习率微调阶段，避免错误续接旧总步数。
- `algo/route_v2_c24_shared.json` 固定实验参数和部署门槛。

## 推荐执行顺序

先运行 dry-run 验证配置：

```powershell
python algo/train.py --styles candy,mosaic,rain_princess,udnie --C 24 --Fc 16 --n_res 4 --norm in --block dw1 --iters 20000 --qat_frac 0.7 --camera_aug_prob 0.75 --temporal_weight 0.01 --temporal_shift 2 --out runs/route_v2_shared --dry_run
```

确认无误后，在 4060 上训练一个独立目录：

```powershell
python algo/train.py --styles candy,mosaic,rain_princess,udnie --C 24 --Fc 16 --n_res 4 --norm in --block dw1 --iters 20000 --qat_frac 0.7 --camera_aug_prob 0.75 --temporal_weight 0.01 --temporal_shift 2 --out runs/route_v2_shared
```

低学习率收尾必须新建目录，不能直接覆盖旧实验：

```powershell
python algo/train.py --styles candy,mosaic,rain_princess,udnie --C 24 --Fc 16 --n_res 4 --norm in --block dw1 --iters 3000 --qat_frac 0 --lr 0.0002 --camera_aug_prob 0.75 --temporal_weight 0.005 --temporal_shift 1 --weights_only runs/route_v2_shared/student.pt --out runs/route_v2_shared_finetune
```

## 判定方法

每个阶段都要在同一批 640×480 内容图上测学生对教师的 PSNR/SSIM，同时保存原画、教师、学生和连续视频拼图。时间损失只有在以下条件同时满足时保留：运动区域不拖影、静止区域闪烁下降、单帧风格纹理没有明显减弱。

训练结果通过后，再用 StyleCam 自己的输入 uint8、逐输出通道 int8、IN 统计刷新、舍入、饱和和系数位宽做整数回放。软件结果不能替代 RTL 对拍。任何新 checkpoint 在硬件组确认之前只属于软件候选，不得覆盖 `rtl/gen/c24_gram_640x480`。

`n_res=5` 和共享主干/独立 d2 bank 仅作结构候选；必须先过完整 Efinity 资源/时序、DDR、IN、风格切换和唯一 frame_id 吞吐测试，才允许生成新的部署 RTL。
