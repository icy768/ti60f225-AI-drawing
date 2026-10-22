# 720p feasibility: unchanged topology NO-GO

Measured core mapping completed13:02 (Efinity2026.1, formal47254c PE12/CFG6). Not whole design PnR or board FPS.

| native size | FF | SRL | ADD | LUT | RAM10 | DSP |
|---|---:|---:|---:|---:|---:|---:|
|640x480|10910|2740|4172|14106|138|141|
|1280x720|10531|2740|4213|13940|219|141|

Sources and SHA in MAP_MEASURED.json; sources and literal geometry diff in SOURCE.json. LUT/FF counts are mapping measurements, not routed XLRs. Both runs map successfully; this alone does not imply720p30 fits or meets timing.

Core RAM increases138→219 (+81). Historical routed whole system minus its engine gives peripheral estimate93RAM/4DSP. Adding that estimate to new core yields312RAM>256, while DSP145<=160. This is a resource feasibility estimate using measured core and historical peripheral accounting, not a new exact whole-design result; no claim of exact XLR from LUT+FF. It leaves no RAM for a drop-in implementation. Independent throughput:30.523392GMAC/s exceeds existing120MAC-lanes@150MHz ideal18GMAC/s, and per-layer scheduling is also over capacity. Unchanged original640 topology at720p30 is NO-GO.

Narrow C16/Fc12 or C14/GI2 variants are research estimates only. C16 last-layerGI4 is still throughput-limited; C14 requires GI/RTL changes. They have no trained art, integer contract, full map/PnR or FPS proof. No720training is authorized. Advanced challenge is UNMET. Camera/HDMI maximum1080p is user-confirmed, so a claim that physical I/O cannot accept720 is withdrawn; buffers/addressing/DDR/OSD/IN statistics and timings still require integration verification. Final16:30 record will restate evidence and any later supervision.

Prior analytical draft is retained below as history; its PENDING statements are superseded by this measured section.

---
# 原生720p30可行性（准备状态，LATEST46 / 123）

13:00开始CPU研究，16:30给最终go/no-go；尚未做完综合、不能宣称高阶挑战达成。不训练720网络。

正式提交47254c25的rtl/stylenet_top.v已单独提取；它的末层PE12/CFG_PE6不同于model/stylenet_top.v的PE6。综合必须用正式rtl版本，不能混用旧生成器PE6报告。源SHA见SOURCE.json；synth_640为参考核心，synth_1280仅宽×2、高×1.5和pixshuf尺寸同步改动，保持拓扑/PE/权重接口，隔离于原工程不出bitstream。

精确解析每层MAC见COST_PRELIMINARY.json：VGA每帧339148800MAC，1104MAC/像素；720p30需30.523392GMAC/s，是VGA30的3倍。逐层PE/DSP吞吐、RAM形状和更窄C16/Fc12、C14/Fc更小方案需继续核算，C14不整除原GI4不能仅改通道数冒充可综合。

待补：核心640/1280 Efinity综合实际LUT/FF/RAM/DSP与映射XLR估算；整机外围93RAM/4DSP/约21972.5XLR为历史层级相减估计，不是新整机PnR。保留相机、DDR、RISC-V、HDMI和时序余量，不把核心能综合当整机go。

硬件组待确认：传感器实际720p30配置/CSI时钟与数据有效、输入缩放/裁剪必须让网络接到1280×720、DDR输入/三输出bank尺寸/地址/带宽、HDMI720p30或更高输出时序、OSD坐标、统计计数位宽与IN常量的像素数、重新整机PnR/CPU-RTL/长稳板测。现代码WIDTH/HEIGHT虽有参数，内部生成网络尺寸硬编码，不能只改sc_engine顶层参数。

当前结论：PENDING_CPU_RESEARCH，高阶挑战未达；没有新资源测量、720p画面或FPS证据。


## 分析初稿（12:52；不是最终go/no-go）

|C/Fc/GI|GMAC/s(720p30)|逐层MAC-lane理想下界合计|行缓存bits / RAM10纯位容量下界|
|---|---:|---:|---:|
|24/16/4|30.523392|208|1116160 / 109|
|16/12/4|19.270656|131|808960 / 79|
|14/8/2|13.077504|94|655360 / 64|
|14/10/2|15.572736|111|706560 / 69|

逐层需求与PE/GI见VARIANT_COST.json。原正式核心共120个INT8乘法lane，150MHz纯乘加上限18GMAC/s；原整机145DSP还包含重定标和其他逻辑，不能用145全部当卷积乘法器。原拓扑720p30需30.523392GMAC/s，**保持PE/时钟不变必不够**。e1/r0d等理想利用需1.659倍，e2/d1a需2.488倍，d1b需2.212倍；忽略装载、requant、IN、DDR停顿仍已超100%，实际只会更差。不能通过“只有3倍像素”推断只需3倍DSP，也不以理论上限代替实测FPS。

逐层MAC最低lane取ceil(MAC/s/150MHz)，相加只给必要资源下界，未计MAC调度、重定标DSP与IN。原方案该下界已经超过整片160DSP的一乘法/DSP实现能力；原RTL没有双INT8 MAC/DSP打包的证据，不假设存在。

C16/Fc12虽总算力下降，末层仍需约8.958GMAC/s，现GI4/PE12最大48lane@150MHz仅7.2GMAC/s；不能只缩通道就承诺30fps。需更大GI/另一并行方式并重做硬件合同、映射和时序，资源尚未实测。C14不整除原GI4，示例用GI2估计，不是原RTL可无改动替换的网络。任何更窄网络艺术效果、训练与量化全部未验证，本次不训练。

行缓存只统计K3的NR×W×CIN×8；原拓扑558080bits→1116160bits，宽倍增；表中RAM是总位数/10240取整的**纯位容量下界**，未按各实例宽深/读口/BRAM颗粒取整，不含MAC权重缓存、pixshuf、IN/DDR/OSD/CPU，也不是整机RAM预测。新核心map与640参考map将给实际映射数据，再讨论外围余量，不能将该下界直接加到旧243宣称精确超限数。
