> LATEST51 17:15已选择本目录作为交付网络（未板测、未完整SoC启动）；下文原第50轮候选时态仅历史，技术范围不变。

# FWP1 原固件CRC常量补丁：本地验证完成，第51轮17:15已选择

时间：2026-10-22T17:09:05.188665+08:00。原RISCV11固件13746B，SHA2319ab969c16850d6fbc750c771cbcfc3d03cd1b76299942e6fb6334c0ecaaca，与历史回退SOURCE一致；没有重新编译。

## 二进制差异

CRC有两个语义用途：启动日志打印模型标识，以及weights_pass比较内部尚未取反的CRC累积值。原常量373deed7变为20d4d7eb；加载器内部比较c8c21128变为df2b2814。分别各一对LUI/ADDI，共四条指令、实际10字节变化，超过监督的“预计≤8字节”估计；只改立即数位，没有改寄存器、操作码、分支、地址、固件长度或其他字节。打印标识也同步更新，不伪装成旧模型。

偏移0x6e4/0x6f0（启动打印），0x1b14/0x1b18（加载比较）；完整字节偏移、旧/新指令见BINARY_RESULT.json，逐行反汇编见DISASSEMBLY.diff。原固件只保留这一处加载器比较和一处日志用途；不需要分支重算。补丁固件SHA6f932ae7dc75ebead8fff869289b41b5dc55c0ff147130188f3f133d2a094408，13746B。

## 实际RV32原二进制加载测试

Unicorn直接执行历史raw RV32二进制，不使用GCC15重编译ELF：weights_load地址f9001b8c，weights_pass及CRC/parser均执行。六例PASS：原固件+原blob4050；原+D1返回-2且零写入；补丁+D1写4050并与blob[16:]逐字节一致；补丁+原blob/损坏D1返回-2且零写；坏头返回-1零写。SPI字节接口/CLINT时间被stub，配置MMIO写入被捕获；不是完整Sapphire/DDR/camera启动，不是板测。

## B布局初值更新与差异定位

在隔离复制的本地B已布线布局上，vendor BRAM updater仅指定CPU system_ramA四个byte-lane初始化文件。XML/place/raminfo/LBF/LPF/接口设置均与B逐字节一致。没有RTL、约束、VG ROM、路由或其他固件改动。

vendor逻辑LBF read核查18个初始化存储器：CPU lane1/2/3分别2/14/16bit变化，lane0不变；其余14个显示/IN ROM全部逐bit一致。四lane重建16384B，与13746B补丁固件加零填充完全一致，见ALL_ROM_LOCALIZATION.json和ROM_READBACK.json。这是vendor逻辑配置读回，不是板上物理读回；压缩BIT的原始字节扩散不能直接当物理区域坐标。

补丁ROM重复更新后PGM配置payload一致，恢复原ROM后payload与原B一致；前256解码文本头生成时间/路径变化，整文件SHA不同，不是A级历史恒等PASS。没有改时间头或归一化伪造SHA。初次全名提取包含physical alias i376，被工具拒绝后停止；修正为18个逻辑名再读成功，失败日志保留。无-b的read仅返回工具头，不作为全存储器验证。

新BIT SHAd05ca9a28994af523131805a1e427a622ce8dcedba1b386bb023052dbdd74475；HEX SHAe357099aa9e3930b558ca453f71d367a279dae8d4909f6febfb181816af6ddd6。新固件只改原常量，无整份重编译风险。资源/时序只引用B原布局56824XLR/243RAM10/145DSP、最小setup+.240/hold+.026ns，不称新PnR测量。新件未完整启动、未板测；交付组合已由监督第51轮17:15明确选择。

## 保留项

原B616e40bb…+D1仍CRC_BLOCKED，不可启动；GCC15固件修复BIT3f302996…保留为备选，整份固件重新生成的额外风险明确保留。原RISCV11 BIT/HEX/blob及原固件SHA未变。没有烧录、外发、上传或合并。
