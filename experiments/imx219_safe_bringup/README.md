# IMX219 安全调通例程（第一阶段：传感器控制）

**状态：代码草案，未接入 Efinity 工程，未在实物板上验证；不要直接烧录或接线。**

本目录重新实现 IMX219 的控制部分，没有复用商家给的 `Ti60f225_imx219hai2hdmi_v7` 工程。两份 Verilog 文件分别实现开漏 I2C 读写和传感器初始化。流程是：电源、复位和 24 MHz 参考时钟由板级电路确保就绪 → 等待 10 ms → 读 `0x0000/0x0001`，必须为 `0x02/0x19` → 逐项写入 1920×1080、双通道、RAW10 配置 → 最后写 `0x0100=1` 开始输出。

默认开启 IMX219 **片内彩条**（`SENSOR_TEST_PATTERN=1`）。这样最终接好 CSI/HDMI 路径时，可先验证传感器及 MIPI 链路，再改为 `0` 测真实画面。`chip_id_ok` 只代表 I2C 识别成功；`config_done` 只代表寄存器写入都收到 ACK；两者都**不代表** MIPI 图像已经到达 FPGA。`error_code`：1=芯片 ID 读取 NACK/总线低电平超时，2=读到的 ID 非 0x0219，3=配置写入 NACK/总线低电平超时。`config_index` 指示配置进度，便于逻辑分析仪定位失败项。

## 为什么目前不生成可烧录的完整工程

官方板卡的 `10_Ti60f225_sc431hai2hdmi_demo` 可作为 HDMI、DDR、CSI 框架参考，但其接收器是 **4 通道**，传感器配置是 SC431HAI；必须在 Efinity 2026.1 里重新生成 **2 通道** CSI RX，并按 IMX219 的 RAW10/字节时钟重新核对处理链。

另一份文件名为 `Ti60F225_IMX219_HDMI_1080P.zip` 的工程，其 `example_top.v` 实际实例化 `I2C_SC2210_19201080_4Lanes_Config`，也不能当成 IMX219 工程烧录。

更关键的是主板 J4 的 **1 脚为 5V**，不能仅凭 22 Pin 针数与现有相机排线直接对插。已有一次反向插线使主板电源灯不亮。现有 RDK 使用说明只介绍 RDK 平台接线和软件使用，没有提供此相机板 **22 Pin FPC 逐脚定义**、排线触点方向和电源转换电路。Sony 的 IMX219PQ 是裸芯片资料，不能代替相机模组原理图。故当前无法安全确定 5V、3.3V、GND、I2C、XCLR、MIPI CLK/D0/D1 的板间对应关系。

## 尚需补齐的信息（向相机商家或板卡商家索取）

1. 你收到的 **IMX219 模组 PCB 型号/原理图**，尤其是外接 22 Pin FPC **1～22 脚的信号、电压、Pin 1 标记、触点朝向**。若 15→22 Pin 是一根排线，也需其 **15 Pin 到 22 Pin 连通表**；排线不一定是逐脚直通。
2. 模组要求的输入电源（3.3V 还是 5V）、是否板载 1.2V/1.8V/2.8V 稳压、I2C 上拉至多少伏、是否有板载 **24 MHz 晶振**、XCLR/使能脚的极性及默认状态。RDK S100 对其 IMX219 模组写有外置 24 MHz 晶振，但不能推断你这块 PCB 必然相同。
3. 板卡的准确型号/版本、准备接 J4 还是 J5、是否能取得官方配套相机转接板的 **电路图**。注意 `CSI2QSE_MIPI` 子卡的 15 Pin 定义也不是通用树莓派 15 Pin 定义，不能仅按针数购买。
4. 如果曾经反插导致主板不上电，最好先在可信平台或经限流的电源/万用表检查相机模块是否仍能被 I2C 读出 `0x0219`；不要再次盲插 FPGA 主板。

这些信息确认后才能把本目录源码接入官方工程，做 J4/J5 引脚约束、复位/电源时序、2-lane CSI RX、帧缓存保护和 HDMI 无信号提示，再编译并上板。

## 仿真（仅控制序列，不包含真实 I2C 波形）

若安装 Icarus Verilog，在本目录执行：

```powershell
iverilog -g2012 -s tb_imx219_bringup -o bringup_tb.vvp rtl/imx219_bringup.v tb/tb_imx219_bringup.v
vvp bringup_tb.vvp
```

该 testbench 用 I2C 桩模块验证 ID 检查、67 项写入、最后开流和测试彩条；它**不验证** `i2c_reg16.v` 的总线时序，实际还需示波器/逻辑分析仪和上板测试。当前机器未找到 `iverilog`/`vvp`，因此以上命令尚未执行；两份 RTL 已用 Efinity 2026.1 的 `efx_map` 完成分析、综合检查，但未布局布线或上板。

## 对照资料

- 本地 Sony `IMX219PQ.pdf`：16～20 页 CSI/CCI，26 页芯片 ID，30～33 页寄存器，63 页彩条，77～78 页上电时序。
- 本地主板 `Ti60F225A_V4_SCH.pdf` 第 11 页：J4/J5 与 J7 引脚；`CSI2QSE_MIPI.pdf`：子卡 15 Pin 定义。
- [Linux 上游 IMX219 驱动](https://github.com/torvalds/linux/blob/master/drivers/media/i2c/imx219.c)：双通道 PLL、裁剪、RAW10 和模式寄存器交叉核对。
- [RDK S100 官方相机接入说明](https://developer.d-robotics.cc/rdk_s_doc/en/Advanced_development/multimedia_development/S100/camera_bringup)：其模块外置时钟说明，仅作线索，不作你收到模组的电路证明。
