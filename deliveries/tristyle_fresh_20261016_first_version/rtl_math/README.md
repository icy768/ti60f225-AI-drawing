# 算术单元 RTL 功能仿真（范围有限）

2026-10-17 09:01，实际 Icarus Verilog 13.0 编译/执行通过。`simulation_result.json`保留命令、日志、源码/向量SHA256及冻结模型包SHA256。

- 91个实际卷积描述符，每个取首/末输出通道，分别测试输入0、零点、255、随机：728个完整点积与重定标用例，47,872个标量MAC。
- 实际图中add/cat常量：360个标量缩放/合并/饱和用例。
- 156个有符号RNE边界用例，包含正负中点、零移位和左移。
- 独立数学预期用Python `Fraction`及最近偶数`round`，不调用整数解释器的舍入实现。测试使用所选包常量，不加载其他网络。

这只证明抽样算术单元的功能一致性，**不是整网RTL验证**。卷积寻址、line/tile缓存、描述符加载、AXI/DDR3、摄像头/显示/帧切换均未集成；没有Efinity综合、时序收敛、LE/DSP/BRAM占用或板上fps。仿真时钟只是驱动激励，不能推断可运行频率。宽组合乘法/移位是参考实现，尚未映射为资源受控流水线。

`rne_shift64`的左移只允许数学结果仍在INT64内；`sh>=64`在INT64输入下最近偶数结果为0。输入零点由u8扩展为有符号9位再相减。累加器在每次MAC时检查33位和的溢出标志。实际模型的全通道范围另见`deployment_refine6000/integer_range_verification.json`。

复现（项目目录，Python3.10）：

```powershell
python supervisor/fetch_simulator.py
python supervisor/fetch_simulator_deps.py
python rtl_math/verify.py
```

下载只解压到`external_runtime/icarus`，不安装全局程序。来自官方MSYS2仓库的版本/字节/哈希见`sources/Icarus_download.json`和`Icarus_runtime_downloads.json`，没有声称验证GPG签名。Icarus是GPL工具，未放进源码便携包；[官方源代码与许可](https://github.com/steveicarus/iverilog)、[官方安装文档](https://steveicarus.github.io/iverilog/usage/installation.html)。首次缺少VPI依赖及仿真零时刻激励问题已修复，最终通过记录是simulation_result.json，不以早期失败日志代替。
