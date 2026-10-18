# 主工程自动曝光试用版 RISCV11

下载 `StyleCam_RISCV11_Main_AE_Only.bit` 到 JTAG/RAM。ID `53430a0b`。

- 保留主工程 CNN、按键和显示布局；本包优先验收 AE，手机预览默认关闭。
- 网络结构、权重和精度保持不变；关闭自动白平衡，RGB 默认 256/256/256。
- Gamma 前的线性 RGB 稀疏测光，中央画面区域；正常 5400 点/帧，RISC-V 每 200 ms 调整一次。
- 复用 APB I²C，3812 分组更新曝光及模拟增益；失败重试并尝试释放分组。
- 保持原 VTS/摄像头帧周期，曝光上限 `2*VTS-12`；不新增图像缓存。
- 资源 XLR 57441/60800，RAM 245/256，DSP 145/160。
- 最终 setup +0.260 ns，hold +0.026 ns。
- 固件使用 16080/16384 B（含 2048 B 栈）；可选语音固件开关未在该版本启用。
- 编译沿用原时钟约束；布局采用 TIMING_3 / seed 0，完整命令记录在 manifest 的 `build_recipe`。
- 摄像头 Gamma 查表拆分与 MHC 公共算术复用；921600 个 RGB/镜像 DDR 像素与参考逐点相同。
- 串口每两秒输出 `AE mean / exp_halfline / gain_idx / i2c_errors / AWB=OFF`，`c` 可读取摄像头寄存器。

离线验证已通过，尚未下载或验收本包。该包用于 JTAG/RAM 观察明暗适应；Flash 保留 RISCV10。
