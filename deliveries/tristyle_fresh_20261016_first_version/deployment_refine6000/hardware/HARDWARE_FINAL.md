# Ti60F225 + DDR3：实际模型计数与参数化估算

EXACT SOFTWARE GRAPH COUNTS + PARAMETERIZED ESTIMATES; NO RTL, EFINITY OR BOARD RESULTS

部署包 `deployment_refine6000\tristyle_v3_hw.bin`：**495552 字节**，包括三专家、共享、偏置、量化常量、图、描述符、头和对齐。

芯片总量160 DSP、320KiB BRAM；CNN参数扫描96/112/128 DSP，预留64/48/32 DSP给其他模块。DDR3物理峰值1.6GB/s，AXI100MHz位宽与实际效率未知。估算使用32/64/128bit及35%/50%/70%有效率，扣除全分辨率RGB采集和显示55.296MB/s。

|输入|风格|GMAC/帧|不融合激活流量 MB/帧（不含halo）|uint8活跃张量峰值 MiB|
|---|---|---:|---:|---:|
|640x480|vangogh|3.5084|207.44|23.44|
|640x480|ukiyoe|2.2967|199.91|23.44|
|640x480|ink|3.3982|212.77|23.44|
|320x240|vangogh|0.8771|51.86|5.86|
|320x240|ukiyoe|0.5742|49.98|5.86|
|320x240|ink|0.8495|53.19|5.86|

MAC为软件图精确计数，1MAC=乘加一次；张量流量每算子落DDR、无原位复用。下表访存另加80px列块内部边界halo估算，外侧零填充由引擎产生。每层权重及量化常量可容于32KiB缓存，大层使用两块16KiB合并驻留，因此不假定下一层同时预取。pointwise须缓存列块的全部输入通道，depthwise按通道组处理。若映射无法保留这些数据、AXI突发填充/转向增加，实际流量更高，需实测。

|输入|风格|仅卷积 ms|含假设重定标 ms|不融合访存 ms|串行 fps估算|理想重叠 fps上界|
|---|---|---:|---:|---:|---:|---:|
|640x480|vangogh|241.0|261.0|606.4|1.15|1.65|
|640x480|ukiyoe|157.7|177.0|583.0|1.32|1.72|
|640x480|ink|233.4|254.2|622.0|1.14|1.61|
|320x240|vangogh|60.2|65.2|151.7|4.61|6.59|
|320x240|ukiyoe|39.4|44.2|146.0|5.26|6.85|
|320x240|ink|58.3|63.6|155.6|4.56|6.43|

表中统一假设112DSP、200MHz、65%利用率、64bit AXI、50%总有效率。并非实测性能。重定标估算另计32×32乘法4 DSP周期/输出、u8×32为2周期/操作数，与卷积共享DSP；具体Titanium DSP映射未验证。

**640×480下15fps未实现。** 对梵高，仅卷积就需要 52.63 GMAC/s；在1MAC/DSP/周期假设下，160DSP×200MHz的全芯片理想上限仅32GMAC/s，尚未预留其他资源。多INT8打包映射尚未验证，不把此假设说成器件所有可能实现的物理上限。

## 可复用算子与缓存设计

固定卷积、分组/深度卷积、方向卷积、ReLU、Q31残差/concat、nearest2共用一个引擎，INT32累加。RGB888接口，激活CHW；摄像头若为交错RGB需要额外行FIFO转换。专家仅在已接纳帧开始时锁存，期间不切换。三专家均包含在同一包中。

当前可执行完整整数网络在CPU运行，尚无整网RTL。后补算术单元MAC/Q31/add-cat/RNE的Icarus功能仿真通过，具体抽样范围见rtl_math/README.md；没有验证寻址、缓存、DDR调度或实际资源映射。建议先逐算子DDR调度，输入通道分块累加，随后验证块内融合；不将未经实现的融合收益计为已达成性能。
- tile_width: 80
- maximum_kernel: 17
- input_channel_tile: 32
- output_channel_parallel: 16
- input_line_tile_bytes: 52224
- partial_accumulator_int32_tile_bytes: 5120
- weights_double_buffer_bytes: 32768
- IO_FIFOs_assumed_bytes: 8192
- current_descriptors_bytes: 144
- all_descriptors_optional_bytes: 15664
- CNN_raw_bytes_streamed_descriptors: 98448
- CNN_raw_bytes_all_descriptors: 113968
- max_single_layer_weights_plus_quant_bytes: 17072
- reserve_sweep: [{'CNN_budget_KiB': 128, 'reserved_nonCNN_KiB': 192, 'raw_byte_fit': True}, {'CNN_budget_KiB': 192, 'reserved_nonCNN_KiB': 128, 'raw_byte_fit': True}, {'CNN_budget_KiB': 240, 'reserved_nonCNN_KiB': 80, 'raw_byte_fit': True}]

以上为原始字节提案。10Kbit块粒度、端口、读写冲突、卷积halo、控制器缓存和布线均待Efinity验证。LUT/LE和实际DSP占用不作伪造估计；最终必须结合摄像头、显示与DDR控制器工程测剩余资源。

## 有界帧率与DDR分配

640×480@30fps持续采集：三个物理原始缓冲分别用于当前计算、最新完整待处理帧、DMA写入。待处理深度永远为1，新完整帧替换旧待处理帧；完成时原子交换地址。显示双缓冲，30Hz重复最新完整输出。若服务时间≤66.7ms可限流接纳每二帧，否则进一步丢帧，禁止累计排队。

320×240内部计算+2倍显示放大属于明确降分辨率模式，不能计为640×480全分辨率15fps。当前各场景只是估算，是否能达到降分辨率15fps仍待调度和板测。

外部原始三缓冲2,764,800B，显示双缓冲1,843,200B，加JSON列出的活跃张量峰值和完整权重；容量可落在256MiB中，容量充足不等于带宽或吞吐达标。RISC-V若采用按软核占用另算。

未验证：整网RTL、综合、P&R、时序、DDR实效、板上帧率、资源占用。未完成：FPGA计算引擎和控制器接入。只有独立算术单元的抽样功能仿真已通过，不改变上述吞吐估算或资源未验证结论。
