# FPS叠加源码核查与板测清单（LATEST46 / 122）

结论：正式RISCV11固定提交47254c25a6e767d7602da96a4529fb84616c9524已有屏幕FPS叠加，不需要因“没有源码实现”而移植V5 OSD。这里证明源码链路，尚不证明当前板上屏幕和固件与该提交逐字节一致，三风格10分钟和断电仍待板测。

## 可复核源码链路

原工程根FPGAProjects/StyleCam_camera；原字节快照、SHA和提交见evidence/FPS_SOURCE/SOURCE.json。

- embedded_sw/soc/software/standalone/stylecam/src/main.c:114–139：osd_draw在第0行第64列显示FPS（一位小数），第20行另显示NN ms、CAM fps和风格。78–89行通过SC_OSD逐字符写APB。
- main.c:148–160：IRQ_PUBLISH触发时frames++，last_pub_t=now()，读SC_JOB_CYCLES。它计完成网络作业并发布的结果，不是摄像头帧数。
- main.c:784–805：dt>=1000000微秒时约每秒重算并osd_draw；fps_x100=发布次数增量×10000000/pub_10us，pub_10us为首末发布时刻差。显示四舍五入到0.1fps；每两个刷新窗口输出串口状态。主循环阻塞会推迟刷新，不能声称精确硬定时1秒。
- CAM独立读SC_SENSOR_FRAMES，按墙钟窗口dt计算；NN耗时为SC_JOB_CYCLES/15000（150MHz，单位0.1ms），不是取1/NN耗时充当FPS。
- rtl/sc_video_schedule.v:43–54：engine_done&&engine_ok进入DRAIN，output_complete&&!pending后产生publish，processed++；失败不发布。
- rtl/ti60f225_oob_top.v:502、516–517把同一publish接到APB IRQ与sc_display。rtl/sc_apb_regs.v:65–66置发布pending并写OSD字符。
- rtl/sc_display.v:134–181：80×23字符，8×16字体放大3倍，双时钟字符RAM和字体流水后叠加RGB，最终接HDMI。故屏幕上已有完整绘制链路。OSD本身包含于原整机55615XLR/243RAM10/145DSP，未独立提取OSD资源，不虚报独立占用。

## 测量边界

该FPS是处理完并提交显示队列的发布率，不是HDMI重复扫描帧率，也不是独立确认每一帧已在屏幕扫出的计数；scan_sequence/scan_timestamp另提供显示退休诊断。IRQ使用pending位，若软件长时间不服务可能合并事件，应同时比较硬件processed、scan_sequence和串口计数。历史34秒19采样29.99–30.01fps为引用串口实测，不能补充不存在的屏幕录像或10分钟证据。

## 给硬件组的板测清单（规格，尚未执行）

1. 记录板号、bitstream/firmware/blob的SHA、CRC和版本；录制完整屏幕含FPS/NN/CAM及风格名称，保存串口原始时间戳。确认当前烧录版本包含上述OSD，且使用640×480网络输入输出；HDMI放大显示不改变网络处理分辨率。
2. VG、UK、ink分别连续运行至少10分钟，包含静态和运动场景；逐秒保存屏幕FPS和发布/processed/scan_sequence计数。风格化输出稳定>=15fps，不能用CAM值替代；记录最小值、均值、停顿和error/overflow计数。补查IRQ计数与硬件计数是否丢事件。
3. 风格切换<100ms：按键/串口请求时刻为t0，以对应新风格首个有效结果发布为t_publish、真实扫描显示为t_scan；保存switch_us、scan_sw_us及原始事件，三风格所有方向重复至少10次。用高帧率录像将按键/指示事件与屏幕首帧对应，报告相机帧率/时间分辨率和最坏值；仅固件写寄存器耗时不算端到端切换。
4. 物理断电再上电一次，录像启动、权重CRC校验、三风格可用和FPS恢复；不把软件复位当断电。
5. 对研究新仿射先解决DEPLOYMENT_HOLD：自主IN gamma/beta ROM当前在位流内，启动M/B替换会被覆盖。未经受支持更新路径及新验证，不以候选blob通过算术门代替持续部署验证。

状态：源码有OSD / 显示发布率 / 约1秒刷新均已核查；新板测、长稳、物理断电未完成。只写规格，无RTL改动、无新bitstream、无烧录。
