# R49 / 134：固件 blob 加载兼容性——现有 B 位流启动阻断

正式提交47254c25a6e767d7602da96a4529fb84616c9524的`embedded_sw/soc/software/standalone/stylecam/src/blob_info.h:7`硬编码`BLOB_CRC32=0x373deed7u`。`main.c:399–402`检查magic=0x53544e31、4050记录和3风格；没有独立版本号检查，保留字读入但未检查。`BLOB_BYTES=48616`用于日志，循环长度由已校验的记录数决定。

`main.c:408`校验整包CRC；`weights_load`（416–420）先执行只读校验再写入。D1实际CRC=20d4d7eb，原固件必定返回-2，零记录写入。`main.c:730–733`显示`WEIGHT BLOB CRC ERROR`并永久停在while(1)，摄像头初始化尚未执行。因此**BIT 616e40bb… + D1blob + 原firmware不可作为可启动的新网络交付**。DP3 B资源/时序PASS仍真实，但不涵盖这条固件启动路径；DP2验证CPU端口记录加载，不执行RISC-V固件CRC逻辑。

修复最小源码改动：仅将blob_info.h第7行改为`#define BLOB_CRC32 0x20d4d7ebu`，保持地址0x200000、长度48616、4050记录、3风格和全部校验逻辑不变。正式`tools.py gen_blob`会从指定blob生成该常量。必须交叉编译、确认除CRC以外语义不变、验证加载路径和DP2写入合同，并将新firmware ROM真正装入新的BIT/HEX。**单独附stylecam.bin不改变已生成位流的片内firmware**，旧B位流SHA不能继续冒充修复版。

实际本地主机C测试：`check_blob_load_r49.py`提取原main.c的CRC/flash_word/weights_pass/weights_load函数，SPI/MMIO由stub替代，仅在写入后记录地址和数据。结果`BLOB_LOADER_TEST/RESULT.json`：原固件+原blob=4050；原固件+D1=-2且0写入；仅CRC常量版+D1=4050且记录逐字节等于blob[16:]；仅CRC版+原blob/损坏D1=-2且0写入；错误包头=-1且0写入。此为主机执行的实际加载器控制流，**不是RISC-V整机仿真或板测**。DP2已有6912像素/936IN系数0LSB，与该4050记录内容相同，但不能称已验证修复版固件启动。

当前未修改DP1/DP3原工程和原B候选。隔离交叉编译/ROM更新验证另存FW_CRC；完成前候选标`FIRMWARE_CRC_BLOCKED`，20:00监督选择需包含本阻断。只改常量仍可解决的路径尚在验证，因此目前不把“硬编码一定拒绝”错误扩大为“无法修复，必须永久回退”。原RISCV11回退完整保留。


## 16点前补充：隔离修复证据，不等于采纳

`FW_CRC/RESULT.json`：仅blob_info.h的CRC源码常量改变，使用公开xPack GCC15.2.0（官方asset SHA核验）分别交叉编译同工具原CRC与D1CRC，均rc0、固件13458B、链接RAM15792/16384B；两新二进制等长、差10字节。历史原固件13746B，与本次不同，不把新编译器归因为唯一差异原因、不称历史固件逐字节复现。正式main.c及DP1/DP3原工程未改；DP1已知工具重写XML单独记录。

`FW_CRC/RV32_LOADER_RESULT.json`：Unicorn执行新编译RV32 ELF真实weights_load/CRC/parser，SPI字节读写和时钟stub，MMIO捕获4050记录。六项正负例通过，记录与D1blob[16:]逐字节一致；该端口数据等于已完成DP2输入。不是完整Sapphire/DDR/camera启动仿真、不是板测、不是新VGA时序测试。

本地B布局BRAM更新生成独立修复BIT SHA3f30299674d8a6b47311ef2749d69a4e10c09aba9665f1fc7e9e0d545df0edd7、HEX SHA8fc0a9be01017de02d5063efdd738dd28fd674ef68d7ad060c425f76467570be。新固件ROM已通过vendor updater装入新LBF，原B文件未改。先原ROM更新得LBF完全相同；生成BIT/HEX整文件SHA不同，差异都在前256解码字节的时间/工程路径文本头，其后配置payload一致。**不是历史A级恒等PASS**。第一次精确容器断言失败如实保留ROM_UPDATE_RESULT；首次生成命令未显式传enable_crc_check，但结果payload仍一致，后续修复生成明确传on。新LBF重复更新的opaque文件SHA不相同，不能据此推逻辑不同；再经vendor PGM证明新固件配置payload幂等，恢复旧固件后配置payload回到B，见PAYLOAD_ROUNDTRIP.json。没有修改时间头或伪造完整SHA相同。

修复件仅本地候选/待监督，新的固件二进制及BIT均未整机启动或板测；资源/时序仅引用B布线（初值更新未重跑PnR），不能宣称新实测56824/+0.240。20:00监督需单独决定是否接受该常量源码+新编译器固件验证链。旧616e40bb…配D1仍明确BLOCKED，不能和新修复SHA混写。
