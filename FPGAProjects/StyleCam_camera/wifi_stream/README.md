# 创意交互：语音切风格 + WiFi 推流到手机

赛题一（AI 赋能实时绘画 / 风格化视频渲染）的**创意交互展示**部分。手势识别按需求暂不做。

**2026-10-30 当前状态：** 三板联调通过并并入主工程正式版（[发布包](../../烧录文件/20261030_RISCV11_PhonePreview_Release/README.md)）。手机端为 **160×120 风格画**：FPGA 按布局截取 640×480 风格画并 4×4 精确平均、RGB332 抖动，分 2 场交错以 3.03 Mbaud 发出（帧格式 `fmt = 0x20 | 段号`，宽高为整帧）；ESP32 收齐两段才发布整帧，网页经 82 端口长连接推流（失败时退回 `/frame.raw?fmt=332&after=<seq>`），实测约 15 帧/s。ESP32 只需重写应用分区 `0x10000`。下文 96×54 等描述为早期记录。

**2026-10-23 状态：** VC-02版本20261023001已烧录，四条命令的模块UART输出各实测一次，20字节均正确；播音仍无声，语音到ESP32/FPGA的完整控制尚待联调。ESP32热点、网页及按钮请求已完成单板验证，手机真实预览尚待整机验证。[完整VC-02项目SDK与配套固件](../../烧录文件/20261021_ESP32_VC02_J7_Integration/voice/sdk/README.md)随本次更新提供；接线及当前可用DIO固件以[三板接入包](../../烧录文件/20261021_ESP32_VC02_J7_Integration/README.md)为准。下文10月19—21日记录按各自日期保留。

**2026-10-19：ESP32-S3-N16R8 已到货，正在做离线接入准备；扩展尚未上板验收。**
**2026-10-21 更新：** 子卡和杜邦线已到货；ESP32 单板已完成 DIO 启动、PSRAM、手机热点和网页按钮验证，
FPGA 新引脚及开启预览的独立候选现已完整构建并通过最终时序；VC-02 项目词条固件待生成，三板联调尚未验收。最新状态见
[软件准备清单](docs/software_preparation_20261021.md)，ESP32 当前使用 [DIO 实板包](../../烧录文件/20261020_ESP32S3_VC02_DIO_BoardTrial/README.md)。
2026-10-20 已补充 [按实物连接的接线清单](docs/wiring_20261020.md) 和
[工具 / 固件准备包](../../烧录文件/20261020_ESP32S3_VC02_Prepare/README.md)。
用户可补买 QSE 转排针子卡，最终方案采用独立 GPIO；电脑 USB 桥接保留为联调辅助。
V4 板的脱机引脚 J7-37 / GPIOL_04 和 J7-39 / GPIOL_06 已通过 Efinity interface 检查；
ESP32 两份原生固件已生成；当前实物使用 DIO/usb_uart，FPGA 新候选见 [三板接入包](../../烧录文件/20261021_ESP32_VC02_J7_Integration/README.md)。
接入方案与接线限制见 [ESP32 / VC-02 离线接入复核](docs/integration_20261019.md)。
本地 V4 板原理图显示：`uart_rx` 已由板载 FT4232HL TX 驱动，`stream_tx` 当前分配的
`GPIOL_01` 接网口 PHY 复位。下文原有逻辑连线不能直接当作实物接线表；
应先选定独立输入及预览引脚，或核实硬件隔离方案，不能把两个 TX 并接。
顶层 `PHONE_PREVIEW=0` 时不实例化手机推流逻辑，`stream_tx` 保持空闲高电平。
需要恢复预览时将该参数设为 `1` 并重新构建；保留的预览已改为 96×54 RGB332。
ESP32 接收后扩展为 RGB565，网页、BMP、MJPEG 与 `/frame.raw` 的像素布局仍为 RGB565。

本目录只做**加法**：不改动已验收的采集—风格迁移—HDMI 链路，从 `sc_display` 的 RGB 输出上
被动抽点，经串口送到 ESP32-S3，再由 ESP32 以 WiFi 推给手机；语音模块则复用现有串口控制台，
实现"说一句话就换风格"。

---

## 1. 数据流

```
                                  ┌──────────────── Ti60F225 (顶层 ti60f225_oob_top.v) ─────────────┐
 SC431HAI ──MIPI──► debayer ──► DDR ──► 13层CNN(V21b) ──► sc_display ──► HDMI/TMDS ──► 显示器
                                                              │ de/vs/red/green/blue（只读抽点，不干预）
                                                              ▼
                                                        sc_stream_tap        每 20 像素取 1、每 20 行取 1
                                                      1920x1080 → 96x54
                                                              │ RGB332 8bit
                                                              ▼
                                                       sc_async_fifo  8bit x 1024（跨时钟：148.5M → 100M）
                                                              ▼
                                                       sc_stream_link      成帧 + CRC16 + 8N1 串口
                                                              │ 3.03 Mbaud
                                                              ▼
                                                          stream_tx ──► 空闲 3.3V GPIO
                                                                                    │
  安信可 VC-02 ──UART 115200──► ESP32-S3 UART2 ─┐                                    │
                                              ├─► ESP32-S3 UART1 RX ◄────────────────┘
  手机浏览器/APP ◄──WiFi(SoftAP)── ESP32-S3 ──┘
   FPGA 串口控制台 uart_rx ◄──── ESP32-S3 UART2 TX（115200，把识别结果转为控制台命令）
```

设计要点：**抽点模块只观察 `de/vs/rgb`，显示链路的行为一字不改**；FIFO 满时丢弃整帧而不是
阻塞显示，所以推流卡顿绝不会影响 HDMI 画面。

---

## 2. 硬件连线

| 连接 | 器件 | 引脚 | 说明 |
|---|---|---|---|
| FPGA | Ti60F225 | `stream_tx` | 现约束为 `GPIOL_01` / BGA R3；V4 板接 PHY 复位，预览应重新选脚 |
| FPGA ↔ ESP32 | ESP32-S3-N16R8 | `GPIO18` (UART1 RX) | 接 FPGA `stream_tx`，3.03 Mbaud |
| FPGA ↔ ESP32 | ESP32-S3-N16R8 | `GPIO17` (UART2 TX) | 115200；接未来独立控制 RX，或已隔离 FTDI 的 `uart_rx` |
| 语音 ↔ ESP32 | ESP32-S3-N16R8 | `GPIO16` (UART2 RX) | 接 VC-02-Kit 丝印 `TX1`，115200；B6/B7 文档差异见复核 |
| 语音 | VC-02-Kit | `RX1` | 本方案不接；平台配置后只需模块输出识别结果 |
| 语音供电 | VC-02-Kit | `VCC` / `GND` | VCC 接稳定 5V（4.5～5.3V，供电能力 >500mA），IO 仍为 3.3V；3V3OUT 是输出 |
| 语音播报 | VC-02 | `SPK+` / `SPK-` | 8Ω 2W 扬声器（官方建议，别用更大功率） |
| 共地 | — | GND | 三块板必须共地 |

> `uart_rx` / `uart_tx` 在现有约束里已占用 `GPIOL_02` / `GPIOR_28`，因此 `stream_tx` 必须
> 另找一个空闲 3.3V GPIO，**不要**和它们复用。

UART1 只接收视频（GPIO18，3030303 baud）；UART2 接收语音（GPIO16）并发送 FPGA
控制命令（GPIO17），两方向均为 115200。不能把控制命令从视频 UART1 发出，否则与 FPGA
控制台的波特率不符。GPIO15 保持不接。USB 转串口适配器的 TX 也不能同时驱动 FPGA `uart_rx`。
V4 的 FTDI 是板载连接，关闭串口软件不能解除电气连接，不能据此认定可以直接并接。

---

## 3. FPGA 侧

### 3.1 新增 RTL

| 文件 | 作用 |
|---|---|
| `rtl/sc_stream_tap.v` | 把 1080p60 光栅抽点成 96×54 RGB332；保留 RGB565 参数兼容，自带节流与丢帧计数 |
| `rtl/sc_stream_link.v` | 从 FIFO 取字，按帧协议打包 + CRC16，用 `uart_byte` 以 8N1 串出 |
| `rtl/ti60f225_oob_top.v` | 顶层新增 `output wire stream_tx`，并在 TMDS 赋值之后例化上面两个模块（`preview_tap` / `preview_fifo` / `preview_link`） |

关键参数（顶层已按 1080p60 配好，若要改分辨率同时改这两处即可）：

- `sc_stream_tap`：`SRC_W=1920, SRC_H=1080, SX=20, SY=20, PACE_WORDS=0, FMT=1`
- `sc_async_fifo`：`W=8, AW=10`，1024 个像素容量
- `sc_stream_link`：`OUT_W=96, OUT_H=54, DIV=33, FMT=1`（`DIV=100MHz/3.03Mbaud`）

### 3.2 Efinity 工程改动（**已完成**）

三处都已经改好并跑通 `interface` / `map` 流程，不需要你在 GUI 里再点：

1. **引脚已分配**。`ti60f225_oob.peri.xml` 里新增了

   ```
   stream_tx  ->  GPIOL_01  (物理引脚 R3, BL 区, 3.3V LVCMOS, output)
   ```

   选 R3 是因为它和现有 `uart_rx`（GPIOL_02，物理 **R4**）**在同一区且 BGA 位置紧邻**，
   但 BGA 球位相邻不能证明排针位置相邻；实际接线需查开发板原理图。工具生成的引脚表：

   ```
   R3,GPIOL_01,stream_tx,Output,BL,3.3 V,3.3 V LVCMOS,,User IO
   R4,GPIOL_02,uart_rx ,Input ,BL,3.3 V,3.3 V LVCMOS,weak pullup,User IO
   ```

   想换别的空闲 3.3V 脚，改 `peri.xml` 那一行的 `gpio_def` 即可（`outflow/*.pinout.csv`
   里信号名为空的行就是空闲脚）。

2. **源文件已登记**。`ti60f225_oob.xml` 的 `design_file` 清单是**手工列的**，新增 RTL
   不会自动进去——漏登记的表现是综合前期直接报
   `instantiating unknown module 'sc_stream_tap'`。已补上 `sc_stream_tap.v`、
   `sc_stream_link.v`、`uart_byte.v` 三项。**以后再加 RTL 文件，记得同步这份清单。**

3. 重新综合/布线即可（软件侧改动见第 5 节）。

### 3.3 资源占用

2026-10-16 资源优化将预览 FIFO 从 RGB565 的 `16×4096` 改为 RGB332 的
`8×1024`，整机综合确认该 FIFO 从 **8 块降为 1 块 RAM10**。代价是预览颜色量化；
96×54 分辨率、网络输入和 HDMI 画质保持不变。相同 AE/ISP 候选启用预览时综合为
246/256 RAM10，关闭时 245/256 RAM10，DSP 均为 145/160。

`PACE_WORDS=0` 只在缓存已空的场边界接收新帧；忙时跳过整个预览帧。1080p60 串口逐像素回归
实测峰值 442/1024，像素时钟加快 1% 时为 490/1024，正常场景均无 FIFO 丢帧或链路中断。
强制溢出测试验证丢弃半帧并重新同步。实机 UART、ESP32 和手机仍需另行验收。

2026-10-15 的 RGB565 布线记录保留在[此前审查记录](../../docs/创意交互审查与资源复核_20261015.md)，
其位流及最终时序不能用于证明当前 RGB332 候选已上板或已通过布线。

### 3.4 构建验证（本机已跑通，非预估）

2026-10-15 RISCV10 / RGB565 集成候选的 interface、map、pnr 和最终时序证据集中在
[审查记录](../../docs/创意交互审查与资源复核_20261015.md)，并附来源哈希。
中间 `place.timing.rpt` 不是最终布线时序；是否可合并以最终 `timing.rpt` 为准。

需要 Efinity 环境（路径按本机实际安装调整）：

```bash
STYLECAM_EFINITY=D:/yilinsiFPGA/efinity/2026.1 python build.py interface   # 或 map / pnr
```

---

## 4. 手机端：三条路，按"要不要装 App"排序

### 4.1 内置网页（推荐，零安装）

ESP32 开一个 SoftAP，手机连上后浏览器打开 `http://192.168.4.1/`：

- 页面自带预览（96×54 放大显示，`image-rendering: pixelated` 保持锐利）
- 风格按钮 **Style 0 / 1 / 2**、**Toggle layout**、**Print status**，直接下发控制台命令
- 实时显示 fps、帧序号、CRC 错误、同步丢失、剩余堆/PSRAM
- 底部 **Voice module** 面板：实时列出语音模块发来的原始字节，用来填 `VOICE_RULES`
  （详见 [`docs/voice_vc02.md`](docs/voice_vc02.md)）

这条路的帧数据走 `/frame.raw`（原始 RGB565，页面用 canvas 展开），
适合答辩现场"不用装任何东西"。

### 4.2 MJPEG：给第三方开源 App 用

装了 `esp32-camera` 库后自动启用 **`http://192.168.4.1:81/stream`**（MJPEG，
`multipart/x-mixed-replace`）。MJPEG 特意放在**独立端口 81 + 独立任务**，
这样 App 长时间拉流不会阻塞 80 端口的控制接口（风格按钮照样能用）。

可直接使用的开源 App 见 **[`docs/phone_apps.md`](docs/phone_apps.md)**，结论速览：

- **VLC**（Android/iOS，GPLv2+）：`打开网络串流` 填 `http://192.168.4.1:81/stream`，装了就能用，最省事
- **niqdev/ipcam-view**（Android，开源）：专门的 MJPEG 查看器，有 demo App 可直接编译
- **perthcpe23/android-mjpeg-view**：适合自己写壳子时当库用

### 4.3 单张快照

`http://192.168.4.1/frame.bmp` 返回一张 24bit BMP，浏览器/图片查看器直接可看，
便于 README 里贴图或截图存档。

---

## 5. 语音控制（模块：安信可 VC-02）

`uart_rx` 这条线本来就是 RISC-V 的串口控制台，所以语音只要能把识别结果变成
`0 / 1 / 2 / v / s` 这几个字符，**RISC-V 命令解析无需修改**。两条路，**建议先用 A**。
物理接线仍须解决上文的板载 FTDI 驱动问题；采用独立 RX 时需要修改 FPGA 顶层和约束。

### A. 经 ESP32 映射（推荐，复用现有 RISC-V 命令）

```
说"梵高风格"
   → VC-02 吐 5 字节  A1 00 01 01 FF
   → ESP32 UART2 收到，按 VOICE_RULES 匹配
   → 映射成 '0' → 经 UART2 TX（115200）转发到 FPGA uart_rx
   → 现有 console() 执行"切到风格 0"
```

**这里有一个必须知道的坑**：VC-02 的串口输出**不是固定协议**——每个命令词发什么字节，
是你在安信可语音开放平台上**一条条手填的**（默认模板 5 字节：
`0xA1 指令开头 | 设备位置 | 设备类型 | 开关状态 | 0xFF 结束`）。所以网上抄来的字节序列
多半对不上，正确做法是**先抓包、再填表**：

- **看串口日志**：说一句话，ESP32 会打印
  `[voice] unmatched: A1 00 01 01 FF   <- put this in VOICE_RULES (config.h)`
  —— 这一行就是**可以直接粘贴的格式**
- **或看网页面板**：内置网页最下方 **Voice module** 面板，勾上后实时列出收到的字节
  （新的在最上面）；也可以直接看 `http://192.168.4.1/voice`

把抓到的字节贴进 `config.h` 的 `VOICE_RULES`（支持 `??` 通配），重新烧录 ESP32 即可：

| 命令词 | 串口数据 | 映射到控制台 | 动作 |
|---|---|---|---|
| 梵高风格 | `A1 00 01 01 FF` | `0` | 风格 0 VAN GOGH |
| 浮世绘 | `A1 00 02 01 FF` | `1` | 风格 1 UKIYO-E |
| 水墨画 | `A1 00 03 01 FF` | `2` | 风格 2 INK WASH |
| 切换画面 | `A1 00 04 01 FF` | `v` | 循环切换布局 |
| 当前状态 | `A1 00 05 01 FF` | `s` | 打印状态 |

匹配规则是**帧长必须完全一致**：`A1 00 01 01 FF` 只认 5 字节，收到 4 字节或 6 字节都不命中。
这是**故意的**——半截帧或混进杂字节的帧如果算命中，就会在莫名其妙的时候把风格切走。
表写错也不用手动上板试：`tools/check_host.sh` 会把 `VOICE_RULES` 逐条编译进去验证。

> `config.h` 里的 `VOICE_MODE` 还有个取值 `2`，是给"直接打印 ASCII 字符"的模块用的
> （比如模块输出 `1` / `2` / `3`）。切换它就能换一种解析方式。

**VC-02 的完整配置步骤**（平台里每一项怎么填、线怎么接、有哪些坑）见
**[`docs/voice_vc02.md`](docs/voice_vc02.md)**。

### B. 语音模块直连 FPGA（可选，编译期开关，默认关闭）

若不想经过 ESP32，可把语音模块 TX 直接接到 FPGA `uart_rx`。此时 `stylecam/src/main.c`
里有一段**编译期开关、默认关闭**的关键词模式：

```bash
# 打开（用 build_fw.py）
STYLECAM_RISCV_BIN=<工具链bin> STYLECAM_EXTRA_CFLAGS="-DSTYLECAM_VOICE_TOKENS=1" python build_fw.py
# 或者直接 make
make STYLECAM_EXTRA_CFLAGS=-DSTYLECAM_VOICE_TOKENS=1
```

打开后先发一次 `t` 进入关键词模式（该模式下单字符命令被忽略，避免单词里的数字/字母误触发），
模块输出的英文单词（空格 / 逗号 / 换行分隔）按表映射：

| 关键词 | 动作 |
|---|---|
| `style0` / `gogh` | 切到风格 0（VAN GOGH） |
| `style1` / `ukiyo` | 切到风格 1（UKIYO-E） |
| `style2` / `ink` | 切到风格 2（INK WASH） |
| `next` | 切换到下一种风格 |
| `layout` | 切换画面布局 |
| `report` | 打印状态 |
| `reload` | 运行中重新从 Flash 装载权重 |
| `raw` | 退回单字符模式 |

**为什么默认关闭**：此前用 xPack GCC 13.4.0 构建 RISCV10，默认 ROM 12218 B、
片上 RAM 14528/16384 B；打开关键词后 ROM 13530 B、RAM 15872/16384 B（96.88%，
含链接器预留栈）。已验证当前源码在同一编译器下关闭开关的二进制与 RISCV10 基线逐字节一致。
厂商流程仍使用原有受验收的 ROM 文件，没有用不同编译器重建的 ROM 替换它们。

当前 AE 固件的链接 RAM 为 16080/16384 B（含 2048 B 栈），关键词模式保持关闭。
上述 RISCV10 的空间余量不适用于 AE 加关键词组合，不能直接同时开启。

---

## 6. 帧协议（`sc_stream_link.v` 与 ESP32 解析器必须一致）

| 偏移 | 字节 | 字段 |
|---|---|---|
| 0 | 2 | `0xA5 0x5A` 同步头 |
| 2 | 1 | type，`0x01` = 视频帧 |
| 3 | 1 | seq，帧序号（256 回绕） |
| 4 | 1 | width（=96） |
| 5 | 1 | height（=54） |
| 6 | 1 | format：`0x01` = RGB332，兼容 `0x00` = RGB565 小端 |
| 7 | 2 | payload 长度，小端：RGB332 为 5184，RGB565 为 10368 |
| 9 | LEN | RGB332 每像素一字节，位布局 `RRRGGGBB`；RGB565 低字节先 |
| 9+LEN | 2 | CRC16 低字节、高字节 |

- CRC：**CRC-16/CCITT-FALSE**，多项式 `0x1021`，初值 `0xFFFF`，覆盖范围**从同步头开始**
  到 payload 结束（即包含 `0xA5 0x5A`）。标准自检值 `"123456789" → 0x29B1`。
- 接收端靠扫描同步头重新对齐，丢一帧不会导致持续失步。
- ESP32 要求类型、尺寸、格式及与格式对应的长度全部匹配，否则视为失步丢弃，
  避免伪造长度造成缓冲区越界。

---

## 7. 构建与烧录

### 7.1 ESP32-S3 固件

Arduino IDE（ESP32 core 3.x）：

| 设置 | 值 |
|---|---|
| Board | ESP32S3 Dev Module |
| PSRAM | **OPI PSRAM**（必须，帧缓冲在 PSRAM） |
| Flash size | 16MB (128Mb) |
| Partition | 16M Flash (3MB APP/9.9MB FATFS) 或 Huge APP |
| USB CDC On Boot | 需要看日志时启用 |

可选：装 `esp32-camera` 库启用 `/stream`（MJPEG）；不装则自动降级，其余功能照常。

WiFi 名字/密码/信道在 `esp32s3_stream/config.h` 改（默认 SSID `StyleCam`，密码 `stylecam1234`）。

### 7.2 RISC-V 固件（只有选第 5 节 B 方案才需要重编）

默认**不需要**重编 —— 语音走 ESP32 映射时，FPGA 固件保持已验收版本不变。
只有启用直连关键词模式时才需要：

```bash
cd FPGAProjects/StyleCam_camera/embedded_sw/soc/software/standalone/stylecam
# 两条路任选其一：
#   1) 打开关键词模式（推荐，不改源码）
STYLECAM_RISCV_BIN=<工具链bin目录> STYLECAM_EXTRA_CFLAGS=-DSTYLECAM_VOICE_TOKENS=1 python build_fw.py
#   2) 直接改 src/main.c 里的默认值
#      #define STYLECAM_VOICE_TOKENS 0   ->  1
```

产物写到 `ip/soc/` 与 `fw_rom/`。注意：**ROM 镜像是环境相关的**，用你本机工具链
重新编译，即使源码一字未改，产出字节也可能与仓库里的不同（本机实测如此）。
所以默认构建**不要**提交这两个目录，以免刷出一堆无意义的二进制差异。

---

## 8. 验证

### 8.1 RTL 仿真（自校验）

```bash
cd FPGAProjects/StyleCam_camera
iverilog -g2012 -o /tmp/stb sim/stream_link_tb.v rtl/sc_stream_tap.v rtl/sc_stream_link.v \
         rtl/sc_async_fifo.v rtl/uart_byte.v
vvp /tmp/stb
```

测试台合成光栅，经 tap → 异步 FIFO → link → 串口接收解码，**逐像素**比对期望 RGB565，
并校验 header / 长度 / CRC。预期输出：

```
PASS tap decimation, framing, CRC and pixel values
tap captured=6 dropped=0 | link frames=5 bytes=13275 aborts=0
```

完整三组用例运行 `python sim_stream.py`（可用 IVERILOG_BIN 指定 Icarus 的 bin）。

需要看波形时加 `-DDUMP`（否则不生成 VCD，避免几十 MB 的中间文件）。

### 8.2 ESP32 固件（不需要 ESP32 工具链）

```bash
cd FPGAProjects/StyleCam_camera/wifi_stream
python tools/check_host.py  # Windows / Linux；也可用 bash tools/check_host.sh
```

共六项检查：

1. 用 g++ 对 sketch 做类型检查（**含** MJPEG 分支）
2. 临时藏起 `esp_camera.h` 再做一次（**不含** esp32-camera 库的降级分支）
3. 用 `-DVOICE_MODE=2` 再编一次（语音字符模式分支，平时不编到）
4. **编译并运行** `tools/host_stub/voice_test.cpp`：把真实的
   `esp32s3_stream.ino` 编进宿主机可执行文件，直接调用里面的匹配函数，
   验证十六进制规则语法、`??` 通配、**帧长不等即不命中**、以及各条
   `VOICE_RULES` 都够得到
5. 跑 `tools/test_frame_parser.py`：用 Python 复现 RTL 成帧规则，喂给与
   `readFpgaTask()` 逐一对应的状态机，验证 CRC 自检值、正常帧逐字节还原、
   坏帧被拒、伪造超大长度不越界

6. 编译运行真实桥接器回归，检查 UART 波特率和路由、CRC 前不发布、非法尺寸/格式/长度、序号回绕和独立快照。

预期结尾：`6/6 host checks PASS`。

---

## 9. 已知限制

- 本次验证包括真实 FPGA 综合/布局布线、RTL 和主机 C++ 回归；没有安装 ESP32 交叉工具链，
  未声称 Arduino 真机编译或 VC-02 / ESP32 / 手机实机联调通过。上板后仍需核对 UART、图像和语音。

- 预览是 **96×54**，是给手机看的"小窗预览"，不是全高清 HDMI 输出；想要更高分辨率
  需要减小抽样步长 `SX/SY`、增大 `OUT_W/OUT_H` 并相应提高波特率（减小 `DIV`），同时复核 FIFO 容量。
- 手机看到的是**降采样**画面，风格迁移效果在 96×54 下细节有限，答辩时建议**大屏 HDMI 看
  效果、手机看交互**。
- `sc_stream_link` 在抽点被中断时会 `DRAIN` 掉当前帧并重新开始，接收端会丢这一帧（已计入
  `/status` 的 `crc_errors` / `sync_losses`）。
- 语音模块型号为**安信可 VC-02**（VC-02-Kit），配置步骤见
  [`docs/voice_vc02.md`](docs/voice_vc02.md)。它的串口输出**由用户在平台上自定义**，
  所以 `config.h` 里那张 `VOICE_RULES` 表**必须按实物抓包结果填**，
  仓库里的默认值是按平台 5 字节模板给的示例，不保证和你手上这块一致。
  好在抓包不需要额外工具：串口日志或内置网页的 Voice 面板就能看到原始字节。

---

## 10. 目录

```
wifi_stream/
├── README.md                     ← 本文件
├── docs/
│   ├── phone_apps.md             ← 开源手机端 App 调研
│   └── voice_vc02.md             ← VC-02 配置、接线、抓包、填表全流程
├── esp32s3_stream/
│   ├── esp32s3_stream.ino        ← 主固件
│   ├── config.h                  ← WiFi / 波特率 / 预览尺寸 / 语音规则表
│   └── web_page.h                ← 内置预览网页（PROGMEM）
└── tools/
    ├── check_host.sh             ← 一键跑下面所有检查（不需要 ESP32 工具链）
    ├── test_frame_parser.py      ← 帧解析器自测（对照 RTL 成帧规则）
    └── host_stub/                ← 宿主机 g++ 检查用的 Arduino 桩头文件
        ├── voice_test.cpp        ← 语音规则匹配自测（编译真实固件代码后运行）
        └── shim.cpp              ← 桩所需的少量符号定义（仅宿主机用）
```
