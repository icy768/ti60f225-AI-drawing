# 创意交互：语音切风格 + WiFi 推流到手机

赛题一（AI 赋能实时绘画 / 风格化视频渲染）的**创意交互展示**部分。手势识别按需求暂不做。

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
                                                              │ RGB565 16bit
                                                              ▼
                                                       sc_async_fifo  16bit x 4096（跨时钟：148.5M → 100M）
                                                              ▼
                                                       sc_stream_link      成帧 + CRC16 + 8N1 串口
                                                              │ 3.03 Mbaud
                                                              ▼
                                                          stream_tx ──► 空闲 3.3V GPIO
                                                                                    │
  安信可 VC-02 ──UART 115200──► ESP32-S3 UART2 ─┐                                    │
                                              ├─► ESP32-S3 UART1 RX ◄────────────────┘
  手机浏览器/APP ◄──WiFi(SoftAP)── ESP32-S3 ──┘
   FPGA 串口控制台 uart_rx ◄──── ESP32-S3 UART1 TX（把语音识别结果当控制台命令转发）
```

设计要点：**抽点模块只观察 `de/vs/rgb`，显示链路的行为一字不改**；FIFO 满时丢弃整帧而不是
阻塞显示，所以推流卡顿绝不会影响 HDMI 画面。

---

## 2. 硬件连线

| 连接 | 器件 | 引脚 | 说明 |
|---|---|---|---|
| FPGA | Ti60F225 | `stream_tx` | 需在 Efinity interface designer 里分配到**空闲 3.3V GPIO** |
| FPGA ↔ ESP32 | ESP32-S3-N16R8 | `GPIO18` (UART1 RX) | 接 FPGA `stream_tx`，3.03 Mbaud |
| FPGA ↔ ESP32 | ESP32-S3-N16R8 | `GPIO17` (UART1 TX) | 接 FPGA `uart_rx`（现有控制台 RX） |
| 语音 ↔ ESP32 | ESP32-S3-N16R8 | `GPIO16` (UART2 RX) | 接 VC-02 的 `B7`(UART1_TX)，115200 |
| 语音 ↔ ESP32 | ESP32-S3-N16R8 | `GPIO15` (UART2 TX) | 可选，接 VC-02 的 `B6`(UART1_RX) |
| 语音供电 | VC-02 | `3V3` / `GND` | 必须稳定 3.3V 且共地，否则识别时会重启 |
| 语音播报 | VC-02 | `SPK+` / `SPK-` | 8Ω 2W 扬声器（官方建议，别用更大功率） |
| 共地 | — | GND | 三块板必须共地 |

> `uart_rx` / `uart_tx` 在现有约束里已占用 `GPIOL_02` / `GPIOR_28`，因此 `stream_tx` 必须
> 另找一个空闲 3.3V GPIO，**不要**和它们复用。

---

## 3. FPGA 侧

### 3.1 新增 RTL

| 文件 | 作用 |
|---|---|
| `rtl/sc_stream_tap.v` | 把 1080p60 光栅抽点成 96×54 RGB565，写入异步 FIFO；自带自限速（`PACE_WORDS`）与丢帧计数 |
| `rtl/sc_stream_link.v` | 从 FIFO 取字，按帧协议打包 + CRC16，用 `uart_byte` 以 8N1 串出 |
| `rtl/ti60f225_oob_top.v` | 顶层新增 `output wire stream_tx`，并在 TMDS 赋值之后例化上面两个模块（`preview_tap` / `preview_fifo` / `preview_link`） |

关键参数（顶层已按 1080p60 配好，若要改分辨率同时改这两处即可）：

- `sc_stream_tap`：`SRC_W=1920, SRC_H=1080, SX=20, SY=20, PACE_WORDS=1024`
- `sc_stream_link`：`OUT_W=96, OUT_H=54, DIV=33, FMT=0`（`DIV=100MHz/3.03Mbaud`）

### 3.2 Efinity 工程改动（**已完成**）

三处都已经改好并跑通 `interface` / `map` 流程，不需要你在 GUI 里再点：

1. **引脚已分配**。`ti60f225_oob.peri.xml` 里新增了

   ```
   stream_tx  ->  GPIOL_01  (物理引脚 R3, BL 区, 3.3V LVCMOS, output)
   ```

   选 R3 是因为它和现有 `uart_rx`（GPIOL_02，物理 **R4**）**在同一区且 BGA 位置紧邻**，
   排针上就在隔壁，接 ESP32 最省事。工具实际生成的 `outflow/ti60f225_oob.pinout.csv`：

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

实测（`build.py map` 的 `outflow/ti60f225_oob.res.csv`）：

| 模块 | FF | LUT | RAM10 |
|---|---|---|---|
| `preview_tap` (`sc_stream_tap`) | 31 | 38 | 0 |
| `preview_fifo` (`sc_async_fifo W=16,AW=12`) | 103 | 82 | **8** |
| `preview_link` (`sc_stream_link`) + `uart_byte` | 149 | 273 | 0 |

FIFO 是 `16bit × 4096`，实测占 **8 块 RAM10**（不是我最初估的 1 块）。
Ti60F225 共 **256** 块 RAM10，本设计综合后 **254/256** —— 装得下，但**余量只剩 2 块**。

> 再省 RAM10 只能连预览尺寸一起缩（例如 64×36 配 `AW=11`，省 4 块）。
> **单把深度降到 `AW=11` 不行**：`sc_stream_tap` 写 FIFO 的瞬时速率远高于
> `sc_stream_link` 的发送速率（3.03 Mbaud ≈ 0.15 字/µs），一场内净增约 2.7K 字，
> 起始占用上限 `PACE_WORDS=1024` ⇒ 峰值约 3.7K 字，2048 深度会频繁写满、
> `tap_drops` 飙升。

### 3.4 构建验证（本机已跑通，非预估）

| 流程 | 命令 | 结果 |
|---|---|---|
| interface | `build.py interface` | **PASS** |
| map（综合） | `build.py map` | **PASS**（RAM10 254/256） |
| pnr（布局布线） | `build.py pnr` | **PASS** |

时序（`outflow/ti60f225_oob.timing.rpt`，所有约束均为正余量）：

| 时钟域 | 约束 | setup slack | hold slack |
|---|---|---|---|
| 全局最差：`sdram_clk`→`sdram_clk`（DDR3，与本次改动无关） | 2.500 ns | **+0.341 ns** | +0.042 ns |
| `hdmi_tx_slow_clk`（`preview_tap` 所在域，148.5 MHz） | 6.734 ns | +1.906 ns | +0.026 ns |
| `core_clk`（`preview_fifo` / `preview_link`，100 MHz） | 10.000 ns | +0.499 ns | +0.026 ns |

新增逻辑**不在关键路径上**，两个自有域都有充裕余量。

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
`0 / 1 / 2 / v / s` 这几个字符，**FPGA 侧一行都不用改**。两条路，**建议先用 A**。

### A. 经 ESP32 映射（推荐，FPGA 侧零改动）

```
说"梵高风格"
   → VC-02 吐 5 字节  A1 00 01 01 FF
   → ESP32 UART2 收到，按 VOICE_RULES 匹配
   → 映射成 '0' → 经 UART1 TX 转发到 FPGA uart_rx
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

**为什么默认关闭**：打开后 ROM 13068 B（+1276 B）、片上 RAM 15376 B / 16 KB = **93.85%**
（其中 2 KB 是固定栈，余量只剩约 1 KB）。已验收的固件在 16 KB 片上 RAM 上已用 85.94%，
为了不给已验收版本带来回归风险，默认构建与验收版本**逐字节一致**（已验证 ROM 镜像完全相同），
功能以开关选装。

> 也就是说：如果你走 A 方案（推荐），`main.c` 里这段代码会被预处理器整体去掉，
> 固件行为和队友验收时一模一样。

---

## 6. 帧协议（`sc_stream_link.v` 与 ESP32 解析器必须一致）

| 偏移 | 字节 | 字段 |
|---|---|---|
| 0 | 2 | `0xA5 0x5A` 同步头 |
| 2 | 1 | type，`0x01` = 视频帧 |
| 3 | 1 | seq，帧序号（256 回绕） |
| 4 | 1 | width（=96） |
| 5 | 1 | height（=54） |
| 6 | 1 | format，`0x00` = RGB565 小端 |
| 7 | 2 | payload 长度，小端（=10368） |
| 9 | LEN | payload（RGB565，低字节先） |
| 9+LEN | 2 | CRC16 低字节、高字节 |

- CRC：**CRC-16/CCITT-FALSE**，多项式 `0x1021`，初值 `0xFFFF`，覆盖范围**从同步头开始**
  到 payload 结束（即包含 `0xA5 0x5A`）。标准自检值 `"123456789" → 0x29B1`。
- 接收端靠扫描同步头重新对齐，丢一帧不会导致持续失步。
- ESP32 侧还额外要求**声明的长度必须恰好等于固定预览尺寸**，否则视为失步丢弃，
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
iverilog -g2005 -o /tmp/stb sim/stream_link_tb.v rtl/sc_stream_tap.v rtl/sc_stream_link.v \
         rtl/sc_async_fifo.v rtl/uart_byte.v
vvp /tmp/stb
```

测试台合成光栅，经 tap → 异步 FIFO → link → 串口接收解码，**逐像素**比对期望 RGB565，
并校验 header / 长度 / CRC。预期输出：

```
PASS tap decimation, framing, CRC and pixel values
tap captured=6 dropped=0 | link frames=5 bytes=13275 aborts=0
```

需要看波形时加 `-DDUMP`（否则不生成 VCD，避免几十 MB 的中间文件）。

### 8.2 ESP32 固件（不需要 ESP32 工具链）

```bash
cd FPGAProjects/StyleCam_camera/wifi_stream
bash tools/check_host.sh
```

做五件事：

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

预期结尾：`5 passed, 0 failed`。

---

## 9. 已知限制

- 预览是 **96×54**，是给手机看的"小窗预览"，不是全高清 HDMI 输出；想要更高分辨率
  需要同时调大 `SX/SY`、`OUT_W/OUT_H` 和串口波特率（`DIV`），并注意 3 Mbaud 的带宽上限。
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
