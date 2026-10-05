# StyleCam：Ti60F225 实时风格化视频（嵌入式芯片与系统设计竞赛 · FPGA 赛道 · 赛题一）

> 2026-10-05 交付默认已切换到 v21b QAT900。部署顶层为 `rtl/gen/v21b_ukiyoe_qat900_640x480/stylenet_top.v`，固件默认 SC431HAI，`vision_top` 默认 1920×1440 RAW10 前端。先阅读 [v21 硬件接入说明](docs/v21_hardware_handoff_20261005.md) 和 [板级集成步骤](docs/板级集成与烧录步骤.md)。`tools/verify_delivery.py` 使用包内 v21 样本复验，无需 COCO 数据。VGA RTL 和本版子系统 map 已通过，完整板级 bitstream/ELF 与实板验收仍未完成。

以下保留历史算法和 IMX219 开发说明；当前交付版本、默认摄像头和验证状态以上述 v21 接入说明及包根 `deployment_status.json` 为准。

> **2026-10-03 最终路线执行记录：** [训练路线](docs/final_route_20261003.md) · [实测结果与部署门槛](docs/final_route_20261003_results.md) · [固定配置](algo/final_route_config.json)。主线仍为 C24/Fc16、4 个 dw1 残差块、IN、共享卷积；新增相机域增强和训练期时间一致性只作用于训练，不改变 RTL 图。候选权重尚未替换现有 RTL，必须完成整数对拍、Efinity 综合、板端帧率和唯一 frame_id 验收后再部署。

## 数据流

```
IMX219 ─MIPI 2lane 912Mbps─► CSI-2 RX(厂商,只放行 DT 0x2B) ─► raw_bin2：1280x960 RAW10 → 2x2 去马赛克
   → 扣黑电平 64 → 白平衡 → sRGB gamma → 640x480 ─► afifo ─► axi_frame_wr ─► DDR 原图缓冲 A[0..3]
                                                        └─► 帧统计 ΣR/ΣG/ΣB/过曝数 ─► CPU 自动曝光 + 灰度世界白平衡
DDR A ─► axi_frame_rd ─► stylenet_top(层融合流式CNN) ─► axi_frame_wr ─► DDR 风格缓冲 B[0..2]
DDR A/B ─► 显示取数(按行) ─► afifo ─► disp_core 720p60 合成(并排/1.5倍全屏)+OSD ─► dvi_encoder(厂商) ─► HDMI
Sapphire RISC-V ─APB3─► vision_core 寄存器：权重装载、风格切换、IN 逐帧刷新、OSD、帧率统计
```

## 目录

| 路径 | 内容 |
|---|---|
| `algo/tinystyle.py` | TinyStyleNet（量化感知训练，条件归一化多风格） |
| `algo/train.py` / `eval.py` | 蒸馏训练（教师 = Johnson 预训练模型）/ PSNR、SSIM 评估 |
| `algo/golden.py` | 整数金标准模型（硬件逐位规格） |
| `algo/gen_rtl.py` | 生成 `stylenet_top.v`、权重/系数初值，iverilog 逐位比对 |
| `algo/export_blob.py` | 导出部署镜像 `net_blob`、固件 IN 常数表 `in_params.h` |
| `algo/test_fw.py` | 固件 IN 刷新逻辑 PC 端验证（MinGW gcc） |
| `rtl/` | swg3 滑窗、mac 乘加、requant、conv_layer、in_stats、axi_frame、axi_arb、raw_bin2（IMX219 前端）、raw_bin3（SC431HAI 前端，保留）、cam_scale3（仿真用 RGB 前端）、disp、vision_core、vision_top；`gamma_srgb.mem`（`tools/gen_gamma.py` 生成） |
| `sim/` | 各模块单元测试、整链路仿真 `run_sys.py` |
| `sw/` | RISC-V 固件：`vision.c` 驱动、`imx219.c` 摄像头、`isp.c` 自动曝光/白平衡、`main.c`、`hal_sapphire.c`（BSP 相关）；`sc431hai.c` 保留未编译 |
| `vendor/` | 厂商 HDMI TX demo（管脚/PLL 参考） |

## 网络（部署模型 `runs/c24_gram`：C=24，4 个单 dw 残差块，IN，4 风格共用卷积权重）

| 层 | 结构 | 输出 |
|---|---|---|
| e1 | conv3x3 s2 3→16 | 320x240 |
| e2 | conv3x3 s2 16→24 | 160x120 |
| r0..r3 | [dw3x3 → pw1x1 +残差] x4 | 160x120 |
| d1a/d1b | 最近邻x2 + dw3x3，pw 24→16 | 320x240 |
| d2 | conv3x3 16→12 + PixelShuffle x2 | 640x480x3 |

1104 MAC/像素（教师 153792），卷积权重 9384 字节，每风格归一化参数 544 个（< 500KB 要求）。

训练：蒸馏（教师 = Johnson 预训练模型）+ L1 + VGG 感知损失 + Gram 纹理损失（2000），2 万步，后 30% 量化感知训练。
对教师输出（60 张 COCO 保留图，640x480 级别）：

| 风格 | PSNR | SSIM |
|---|---|---|
| candy | 16.18 | 0.456 |
| mosaic | 14.41 | 0.388 |
| rain_princess | 16.44 | 0.440 |
| udnie | 19.01 | 0.654 |

对照实验：单风格独立训练（mosaic 15.24/0.421）与 4 风格共用（15.14/0.416）画质相同，故共用权重；
Gram 损失使 PSNR 略降但颜色饱和度与笔触纹理明显更接近教师（`docs/old_vs_gram.jpg`）。
部署文件：`rtl/gen/c24_gram_640x480/`（RTL + 权重/系数初值 + `net_blob.bin`），`sw/net_blob.h`、`sw/in_params.h`。

## 验证（全部与金标准逐位一致）

一键回归（9 项，约 2.5 分钟，日志在 `sim\work\regress\`）：

```powershell
powershell -ExecutionPolicy Bypass -File tools\regress.ps1
```

Efinity 综合（只跑 map，Ti60F225 I3，约 1.5 分钟，报告在 `syn\outflow\vision_map.res.csv`）：

```powershell
cd syn; efx_run vision_map.xml --prj --flow map
```

逐层单独综合（定位综合器问题用）：`cd syn; ..\.venv\Scripts\python bisect_layers.py [层号...]`

单项命令：

```bash
cd sim; python run_swg3.py                         # 滑窗 8 组
cd sim; python run_scale.py                        # 摄像头降采样
cd sim; python run_motion.py                       # 运动检测
cd sim; ../.venv/Scripts/python run_rawbin2.py     # IMX219 前端 5 组（Bayer 相位/黑电平/增益/gamma/跳行/无间隔满速）
cd sw; gcc -O2 -I. test/isp_test.c isp.c -lm -o test/work/isp_test.exe; ./test/work/isp_test.exe   # AE/AWB 闭环 7 场景
# .venv 是瘦环境，torch/torchvision/numpy 等通过 .venv/Lib/site-packages/_shared_torch.pth 用 claudeProject\pytorch_env
cd algo; ../.venv/Scripts/python gen_rtl.py --W 48 --H 32 --stat_layer 5 --load_weights   # 整网+统计+装载
cd sim; ../.venv/Scripts/python run_sys.py         # 整链路：摄像头→DDR→NN→DDR→HDMI+OSD+APB
cd algo; ../.venv/Scripts/python test_fw.py        # 固件 IN 刷新
```

## 性能估算（150MHz，640x480）

| 层 | 每输出像素周期 | 折合每输入像素 |
|---|---|---|
| e1 (PE=4) | 36 | 9 |
| e2 (PE=4) | 216 | 13.5 |
| r*a dw | 54 | 3.4 |
| r*d pw (PE=1) | 144 | 9 |
| d1a dw | 54 | 13.5 |
| d1b (PE=2) | 48 | 12 |
| d2 (PE=6) | 72 | 18 |

瓶颈 d2 每输入像素 18 周期（为省 BRAM 由 PE=12 降到 6）；仿真实测稳态 18.42 周期/像素
（`gen_rtl.py --W 64 --H 48/96 --rin 1 --rout 1000000` 两次之差），NN 时钟 150MHz 约 26.5fps、100MHz 约 17.7fps。
requant 每通道占 2 拍（系数半字交替读），各层每像素周期均 ≥ 2×COUT，不构成瓶颈。
乘法器 117 个（8x8 96 个，宽乘法 21 个），Ti60 共 160 DSP。
风格切换最坏延迟 ≈ 当前帧剩余 + 新风格一帧 + 显示取帧 ≈ 28+28+17 ≈ 73ms（< 100ms）。

## 资源实测（Efinity 2026.1.132.4.5 综合，Ti60F225 I3，2026-09-30）

| 部分 | M10K | DSP | XLR（布局后） | clk_nn Fmax |
|---|---|---|---|---|
| 视觉子系统，优化前 | 239 | 144 | — | — |
| 砍 BRAM 后 | 167 | 120 | 55591 | 141.5MHz |
| **砍逻辑后（当前）** | **172** | **120** | **37322**（61%） | **201.7MHz** |
| 厂商 IP 预计（SoC 43、DDR3 不加跨时钟桥 22、CSI 像素 FIFO 512 深约 8、HDMI 2） | 约 75 | 4 | 约 18000 | — |
| **合计 / Ti60 总量** | **约 247 / 256** | 124 / 160 | **约 55300 / 60800（91%）** | — |

当前其它时钟 Fmax：clk_axi 216MHz、clk_cam 230MHz、clk_pix 275MHz（仅 vision_top 布局布线，未加厂商 IP、无 SDC，I3；
跨时钟路径为 CDC，正式工程需在 SDC 里设为异步组）。NN 200MHz 对应约 35fps，150MHz 约 26.5fps。

M10K 物理为 512x20（最宽 20 位，真双口每口最宽 10 位），宽而浅的存储器很浪费。所有优化均保持逐位一致（回归 9/9）：
- 砍 BRAM：行缓冲深度 >2048 且非 2 的幂时拆两段；AXI FIFO 只存 96 位；权重整行写入；d2 PE 12→6；
  系数拆 19 位半字交替读（requant 每通道 2 拍，各层每像素周期 ≥ 2×COUT，不影响吞吐）。
- 砍逻辑（小存储器改用 XLR 的 SRL8 移位链或 M10K）：mac_dense 环形累加器按序访问 → 长 NF 的移位延迟线；
  输出缓存、残差旁路字节、层间 sfifo → `srlfifo`/移位链 FIFO（按占用数动态读）；
  swg3b 待提交缓冲 → 两条移位链（位置 = 本行已写字数 − 1 − (列×NG+组)）；IN 统计累加器 → M10K 读改写。
- 时序：IN 统计单元入口加一拍（原 requant 组合输出 → 13 选 1 → 平方乘法器是 NN 关键路径），clk_nn 125→202MHz。
- requant 中间和 48→40 位（和 < 2^36，不溢出）。

综合器问题（已修）：`mac_dense` 残差旁路 `sbank` 原写成每拍 G 个写口的存储器数组，efx_map 在顶层展平时崩溃
（EXCEPTION_ACCESS_VIOLATION）；改为 generate 常量下标寄存器后通过，回归逐位一致。

## 资源估算（`tools/estimate.py`，综合前，已被上表实测取代）

| 部分 | M10K |
|---|---|
| NN（行缓冲 59、权重 30、系数 13、输出重排 3；stride1 层 2 行缓冲 swg3b、上采样层 2 行） | 108 |
| 视觉子系统合计（含摄像头前端 raw_bin2 7 块、运动检测、跨域 FIFO、OSD、AXI FIFO） | 146 |
| 厂商 IP（CSI RX、DDR3 控制器、Sapphire）预计 | 70~90 |

Ti60 共 256 块，**BRAM 是最紧的资源**。富余不足时的缩减手段（按代价从小到大）：
AXI FIFO 改为 32 位像素宽（约省 12）→ 瓶颈通道 C 24→16（约省 20，画质有损）。已做：2 行行缓冲（省 29）。

## IN 的硬件实现（分时统计 + 乒乓系数槽）

流式硬件拿不到当前帧的均值方差。`in_stats` 每帧只统计一层的逐通道 Σa、Σa²（整数，逐位确定），
CPU 算出该层 M/Bq 写入非活动系数槽再切换（下一帧生效，帧内不撕裂），12 个 IN 层轮流刷新。
静止画面下 1 轮（12 帧，25fps 约 0.5s）即与逐帧 IN **逐位一致**（`algo/sim_in_refresh.py`）；
固定统计量方案对逐帧 IN 仅 17.6dB。

## 时钟域

摄像头（厂商像素时钟）、AXI（DDR 用户时钟，软核 DDR3 预计约 100MHz）、NN（`NN_ASYNC=1` 独立时钟，目标 150MHz+）、
像素（74.25MHz）。NN 数据经异步 FIFO、控制脉冲经翻转同步跨域；整链路仿真在四个不同频时钟下逐位通过。

## 互动

- 挥手切风格：`motion_det` 对摄像头流做 16x16 分块亮度帧差，CPU 跟踪运动质心横向轨迹（<35%→>65% 右挥）。
- 按键：KEY0 风格、KEY1 显示模式、KEY2 IN 刷新、KEY3 NN 开关。
- 串口：`0-9` 风格、`n` 下一风格、`m` 显示模式、`i` IN 刷新、`o` NN 开关、`s` 状态（帧率、Y 均值、曝光、增益、白平衡）、
  `a` 自动曝光/白平衡开关、`e`/`E` 手动曝光 ×7/8、×9/8、`f` 翻转循环（无→水平→垂直→都翻）、`t` 彩条测试图、`k` 帧首跳行 0/2。

## 寄存器（APB，字节偏移）

见 `sw/vision.h`。要点：`0x004` 使能/模式，`0x008` 系数槽（风格 s 用槽 2s/2s+1），`0x020-0x028` 权重与系数写口，`0x040-0x054` IN 统计，`0x800-0xFFF` OSD 文字。

摄像头前端：

| 偏移 | 内容 | 复位值 |
|---|---|---|
| 0x06C | CAM_BAYER[1:0]：左上像素颜色 0=R 1=Gr 2=Gb 3=B（IMX219 翻转值 h\|v<<1 即为此值） | 0 |
| 0x070/0x074/0x078 | 白平衡增益 R/G/B，8.8 定点 | 440/273/420 |
| 0x07C | CAM_CTRL：[9:0] 黑电平、[12] gamma、[17:16] 帧首跳过行数、[24] 模组使能（cam_en 脚） | 64、1、0、0 |
| 0x080/0x084/0x088 | 上一帧 640x480 的 R/G/B 之和（sRGB 8 位） | 0 |
| 0x08C | 任一通道 ≥250 的像素数 | 0 |
| 0x090 | 统计帧序号（帧写入 DDR 完成时加 1） | 0 |

## 摄像头：亚博 RDK MIPI 高清摄像头（Sony IMX219）

| 项 | 取值 |
|---|---|
| 传感器 | IMX219PQ，3280x2464，RAW10，Bayer RGGB（无翻转），黑电平 64，I2C 7 位地址 0x10，ID 0x0219 |
| 接口 | MIPI CSI-2 2 lane，912Mbps/lane（字节时钟 114MHz），INCK 24MHz（模组板载） |
| 模式 | 2x2 模拟合并，居中窗口 2560x1924（全幅 78%）→ 输出 1280x962；行长 3560；帧长 1708（单位 2 行）→ 30fps |
| 曝光 | 1 行 = 19.52us，1..1704 行；≥10ms 时取 10ms 整数倍（防 50Hz 灯光横条），最长 1536 行 = 30ms |
| 增益 | 模拟 256/(256-X)，X 0..232（≤10.67 倍）；数字 4.8 定点 ≤2 倍 |
| 嵌入数据 | 每帧开头 2 行 DT 0x12：CSI RX 按 DT 0x2B 过滤；过滤不了时 CAM_CTRL.skip=2（多出的 2 行正好补齐 960 行） |
| 寄存器表来源 | Linux 主线 `drivers/media/i2c/imx219.c`，PLL/时序与厂商 `vendor/10_Ti60f225_sc431hai2hdmi_demo/v6/Ti60f225_sc431hai2hdmi_v6/rtl/cam/piv2_*_2L_reg.mem` 一致；手册在同目录 `doc/IMX219PQ.pdf` |

上电顺序（`main.c`）：`cam_en`=0 保持 10ms → `cam_en`=1 → 等 10ms（手册要求 ≥6.2ms）→ 读 ID → 写表 → 开流 → `isp_init`。

### 硬件连接：不能直接插板上 J4/J5

板上 J4/J5（22 针 0.5mm，AFC01-S22FCC-00）是厂商给 SC431HAI 模组定义的，与树莓派 5/RDK 的 22 针定义不同：

| J4 脚 | 网络 | FPGA |
|---|---|---|
| 1、5 | **VCC_5V** | — |
| 2 | Sensor_SDA（4.7k 上拉到 **3.3V**） | GPIOR_18 |
| 3 | Sensor_SCL（4.7k 上拉到 **3.3V**） | GPIOR_20 |
| 6 | Sensor_RST | GPIOR_16 |
| 17/18 | MIPI_D21_N/P | GPIOT_PN_07（厂商 cam_d0） |
| 11/12 | MIPI_D22_N/P | GPIOT_PN_10（厂商 cam_d1） |
| 14/15 | MIPI_CK2_N/P | GPIOT_PN_09（厂商 cam_ck） |
| 20/21 | MIPI_D20_N/P | GPIOT_PN_06（厂商 cam_d2，IMX219 不用） |
| 8/9 | MIPI_D23_N/P | GPIOT_PN_11（厂商 cam_d3，IMX219 不用） |
| 4、7、10、13、16、19、22 | GND | — |

亚博这款 IMX219 的 I2C/使能是 **1.8V 电平**（RDK S100 摄像头扩展板文档："亚博 1.8V / 微雪 3.3V"），供电 3.3V。
直接插 J4 会把 5V 加到模组的 3V3 脚和 CAM_IO1 脚、把 3.3V 上拉加到 1.8V 的 I2C 上；差分对的位置也不一样（极性要按模组原理图核对）。
需要做一块 22 针转 22 针的转接板：

| 模组信号 | 转接板 | J4 |
|---|---|---|
| 3V3 | 5V → 3.3V LDO（≥300mA） | 1（5V） |
| GND | 直连 | 4、7、10…22 |
| D0_P/N | 100Ω 差分直连 | 18/17 |
| D1_P/N | 同上 | 12/11 |
| CK_P/N | 同上 | 15/14 |
| D2、D3、CAM_IO1（LED/MCLK） | 悬空 | — |
| SDA、SCL | PCA9306 双向电平转换（1.8V ↔ 3.3V，1.8V 由 LDO 提供） | 2、3 |
| CAM_IO0（使能/XCLR） | 3.3V→1.8V 单向转换（如 74LVC1T45 或 10k/12k 分压） | 6 |

模组侧 22 针的排序以模组丝印/RDK X5 原理图（`RDK_X5_IO_CONN_PUBLIC_V1.1.pdf`）为准，接线前用万用表确认 GND 与 3V3 脚。

## 板级集成（进行中）

厂商资料：`D:\QQ Files\Ti60F225_DemoBoard_v4完整资料包.zip`，已解出到 `vendor/`：
`10_Ti60f225_sc431hai2hdmi_demo/v6`（摄像头→HDMI）、`08_ti60f225_soc_demo/09_Ti60F225_hardjtag_demo`（Sapphire SoC）、原理图。

从厂商工程核实的参数：
- DDR3 软核控制器 `ddr3_top`：AXI 128 位数据/32 位地址/4 位 ID，AXI 时钟 `core_clk` 100MHz（与 DDR 异步）。
- CSI RX（`efx_csi2_rx` 5.16）：像素时钟 `i_mipi_rx_pclk` 50MHz，每拍 4 个 RAW10（`pixel_data[39:0]`，Pack_40），vsync 以跳变沿判帧。
- 厂商工程里还有 IMX219 的配置（`rtl/cam/piv2_config.v` + `piv2_*_2L_reg.mem`，I2C 地址 0x10），PLL 与本工程一致。
- HDMI：USER_PLL VCO 2970MHz，`vid_clk_dvi2`=74.25MHz；720p60 需把串行化慢/快时钟分频 20/4 改为 40/8。
- Sapphire：RV32IM 100MHz，程序在 DDR；`IO_APB_SLAVE_0_INPUT`=0xf8100000；DDR 口 `io_ddrA_*`（128 位、8 位 ID）。
  `sw/hal_sapphire.c` 已按该 BSP 的真实函数（`i2c_writeData_w/readData_w`、`uart_*`、`gpio_getInput`）改写。

集成方案：保留厂商 CSI RX、DDR3 控制器、`dvi_encoder`（加密核）、SoC；去掉厂商 RAW 帧缓存/Debayer/伽马/DSI/RTL I2C；
CSI 输出直接进 `raw_bin2`（`vision_top` 默认 `CAM_RAW=2, IW=1280, IH=960`）；
SoC 与视觉子系统两个 AXI 主口经仲裁接 DDR；NN 时钟取空出的 MIPI_TX_PLL 输出（125MHz 起步）。

IMX219 相对厂商 SC431HAI 工程的改动：

| 位置 | 厂商值 | 改为 |
|---|---|---|
| CSI RX IP `NUM_DATA_LANE` | 4 | 2 |
| CSI RX IP `HS_BYTECLK_MHZ` | 50 | 114 |
| CSI RX IP `MIPI_CSI2_RX_PIXEL_SIDEBAND` | 1'b0 | 1'b1，`cam_valid = pixel_data_valid && datatype == 6'h2B`（按 IP 手册核对 datatype 与像素是否同拍；不同拍则保持 1'b0，改用 skip=2） |
| CSI RX IP `tHS_SETTLE_NS`、`DPHY_CLOCK_MODE` | 125、Discontinuous | 不变（912Mbps 时窗口 91.6~156ns；IMX219 为非连续时钟） |
| peri.xml MIPI RX 通道 | cam_ck PN_09、cam_d0 PN_07、cam_d1 PN_10、cam_d2 PN_06、cam_d3 PN_11 | 删掉 cam_d2、cam_d3；`Rx_HS_D_2/3` 悬空，LP/使能/FIFO 总线改 2 位 |
| peri.xml RX 通道 `delay` | 17（400Mbps 下调好） | 912Mbps 下重新扫（看 `mipi_debug_out` 的 CRC/ECC 错误位） |
| I2C | RTL `i2c_master_ctrl_top` 接 GPIOR_20/18 | Sapphire `SYSTEM_I2C_0` 接 GPIOR_20（SCL）/GPIOR_18（SDA） |
| 传感器复位 | RTL 计数器 | `vision_top.cam_en` 接 GPIOR_16 |

上板顺序：串口看 `IMX219 ok` → 按 `t` 出彩条（验证 lane、像素顺序 p0 在低位、Bayer 相位）→ 再按 `t` 回实景 →
顶行有杂点按 `k`（嵌入数据行未滤）→ 画面倒置/镜像按 `f` → `s` 看 AE/AWB 是否收敛到 Y≈115。
