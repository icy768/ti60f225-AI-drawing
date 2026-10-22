# 交付后板测清单：本轮仅规格，未执行

LATEST51 17:15已选择candidates/D1B60_B_FWP1/。使用FINAL_DECISION.md完整SHA与MANIFEST.json核验的配套BIT/HEX/固件/blob，CRC20d4d7eb。原B616e40bb…+D1不可启动；GCC15修复不是选定版本。原RISCV11回退配CRC373deed7。以下由交付后操作者执行，本自动任务不烧录。

## 文件、地址与工具来源

- 正式源码：47254c2，`program_main_ae_flash.py`、`flash_blob.py`、`program.py`、README。Flash配置从地址0开始；blob在0x200000（十进制2097152），48616字节，头magic/记录数4050/风格数3。配置HEX为逐字节文本，先解码验证配置区长度及64KiB向上取整擦除范围均小于0x200000，不能用HEX文本大小代替Flash占用。
- 工具：安装目录`<EFINITY>/pgm/bin/ftdi_pgm.bat`；桥接位流`<EFINITY>/pgm/fli/titanium/u10660A79.bit`；board profile=`Generic Board Profile Using FT4232H`。先`-l`枚举实际唯一设备URL，用实际`<URL>`，不沿用历史USB端口号。
- 原烧录脚本核验历史release的硬件验收和SHA，故不能直接把研究候选塞入后绕过断言；禁止伪造`hardware_verified`。下面列出同源底层命令规格，须使用最终配套SHA并保存完整日志。

## 配套新版本烧录和启动

1. 核验最终BIT、HEX、blob及固件ROM的SHA，确认CRC20d4d7eb常量补丁进入最终位流；记录板卡、工具版本、串口、供电。先备份Flash配置和0x200000模型区域，并核对备份可回读。不能在桥接运行时把相机无输出当网络故障。
2. 从正式脚本使用的CLI枚举`ftdi_pgm.bat -l`。每次需访问Flash先加载桥接：`ftdi_pgm.bat -m jtag -u <URL> -b "Generic Board Profile Using FT4232H" --jtag_clock_freq 1000000 <EFINITY>/pgm/fli/titanium/u10660A79.bit`。
3. 转换最终blob为每行两位十六进制的`net_blob.hex`（字节顺序不变）。按同源命令写入：`ftdi_pgm.bat -m jtag_bridge -u <URL> -b "Generic Board Profile Using FT4232H" --jtag_clock_freq 1000000 --address 2097152 --jtag_bridge_mode all --verify_method hostx1 <net_blob.hex>`。保存日志。
4. 在同一桥接下写最终配置HEX到地址0：相同参数，`--address 0 --jtag_bridge_mode all --verify_method hostx1 <final.hex>`。配置和模型写入任一失败均停止启动测试、保存原始日志；不要混用旧firmware与新blob。
5. 分别独立回读两区域：相同`jtag_bridge`参数，改`--jtag_clock_freq 500000 --jtag_bridge_mode read --num_bytes <actual decoded length> -o <readback.hex>`；模型长度48616。解码逐字节比较最终文件，记录SHA。仅CLI报告verify不替代独立回读。
6. 打开115200 8N1串口监听后按RESET_N重新装载Flash；桥接之后必须重新配置。保存从复位起完整日志：模型CRC20d4d7eb、4050条记录、无CRC错误、camera初始化成功、三风格ready=7。记录实际BIT/固件/blob绑定，不能借用原RISCV11启动日志。

## 验收采样

- UART `0/1/2`选择VG/UK/ink，`v`布局、`s`状态、`c`相机；KEY3短按释放切风格，长按约0.7秒切布局。来源正式README及main.c。
- 原生网络640×480，三种风格各连续至少10分钟。屏幕同时显示网络结果发布FPS和CAM信息，读取**网络**FPS；保留完整带时间屏幕录像和串口原始日志，计算最小值、均值、样本数，要求每个有效网络FPS读数≥15。不能用HDMI60Hz、摄像头FPS、CPU golden推理速度或历史30fps代替。
- 记录`proc/cap/skip/run_skip`、AE I²C及采集/显示错误增量、所有停顿、起止时间。10分钟测量前待启动/IN稳定，不能删除稳态低值。分屏/三联布局单独标记，不推定所有布局均通过。
- 切换：覆盖0→1→2→0及反向，多次采样。区分普通UART/按键风格切换和完整blob重载。保存命令/按键事件起点、SC_SCAN_TIMESTAMP/SEQUENCE/STYLE对应的新风格首帧事件，以及外部屏幕采样；报告`switch_us/scan_sw_us`和端到端原始时间。每次完整目标切换<100ms；超过或原始采样不足则FAIL/未验证。源码pause_stream有120ms idle，**不要把普通bank切换计数当完整两次SPI/CRC重载<100ms证据**。
- 断电：停止供电、恢复供电，记录供电方式、断电间隔、从上电开始的串口与屏幕；无需先JTAG载入，模型正确、三风格可用、OSD网络FPS恢复。RESET_N通过不等于物理断电通过。
- VG画面对照：同光照/曝光/场景拍红衣和肤色，原版与D1并排，记录红色是否被变橙/橄榄、人脸是否青绿/白斑；同时检查纹理软化、物体结构、闪烁。弯曲笔触/颜料块仍为艺术缺口，色相收益不能冒充最终艺术达标。

## 回退

使用`rollback_RISCV11`内原BIT（SHA0b7c2d11…）、原HEX和原blob（SHA9a1b2382…、CRC373deed7）。先复核最终回退MANIFEST，按以上桥接、两个地址写入、独立回读、监听后RESET_N/断电流程恢复**配套原配置和原blob**。不能只回退blob而保留CRC20d4d7eb固件，也不能只回退BIT而保留D1blob。

正式历史源码的`program_flash_release.py --check-only`/`program_main_ae_flash.py --check-only`仅用于它绑定的完整原release；若使用这些入口，必须在未改的正式树与原完整release上执行其检查。当前交付复制件的布局与历史完整release不同，不能声称原脚本可无修改直接烧录复制目录。

以上均待交付后实际执行。历史RISCV11 29.99–30.01fps是引用，覆盖约34秒；新版三风格各10分钟、物理断电、完整切换<100ms尚未验证。
