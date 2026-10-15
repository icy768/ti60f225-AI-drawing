# 开源手机端显示 App 调研

> 需求：ESP32-S3 是**视频服务端**（提供 MJPEG / 原始帧），手机需要的是**客户端查看器**。
> 这一区分很重要，见下面的"注意"。

---

## 0. 先说结论

| 优先级 | 方案 | 平台 | 开源协议 | 是否要装/编译 | 适配我们的 `/stream` |
|---|---|---|---|---|---|
| **1（推荐）** | **本仓库内置网页** | 任意浏览器 | 本仓库自带 | 不用装 | 直接可用 |
| **2（推荐）** | **VLC** | Android / iOS / 桌面 | GPLv2+ | 商店直接装 | 直接可用 |
| 3 | **niqdev/ipcam-view** | Android | MIT | 需自己编译或写壳 | 直接可用（标准 MJPEG） |
| 4 | **perthcpe23/android-mjpeg-view** | Android | MIT | 当库用，写个壳 | 直接可用 |

**给答辩的建议**：现场演示用第 1 条（浏览器打开就没风险，不用装任何东西），
备一台装了 VLC 的手机做第 2 条。第 3/4 条是"如果一定要一个独立 App 图标"时的选择。

---

## 1. 方案 1：内置网页（首选）

ESP32 固件里已经把预览页编译进 flash（`web_page.h`，PROGMEM），手机连上 SoftAP 后：

```
http://192.168.4.1/
```

- 96×54 预览放大显示，`image-rendering: pixelated` 保证不糊
- 风格按钮 / 切换布局 / 打印状态，直接下发 FPGA 串口命令
- 实时 fps、帧序号、CRC 错误计数

**优点**：零安装、零依赖、跨平台（Android/iOS 都行）、控制+显示一体。
**缺点**：是个网页而不是 App，没有桌面图标。

---

## 2. 方案 2：VLC（最省事的原生 App）

VLC 是开源播放器，原生支持 `multipart/x-mixed-replace` 的 MJPEG 流：

1. ESP32 装了 `esp32-camera` 库（启用 `/stream`）
2. 手机连上 `StyleCam` 这个 WiFi
3. VLC → **网络串流 / Open Network Stream** → 填
   ```
   http://192.168.4.1:81/stream
   ```

- Android：`org.videolan.vlc`（Google Play / F-Droid）
- iOS：VLC for Mobile（App Store）
- 协议：GPLv2 及以后

**优点**：装了就能用，跨平台，稳定性好（解码器是 VLC 的，不是我们的）。
**缺点**：UI 是播放器不是摄像头面板，看不到 `/status` 那些计数。

---

## 3. 方案 3：niqdev/ipcam-view（Android，专门做 MJPEG 客户端）

- 仓库：https://github.com/niqdev/ipcam-view
- 协议：**MIT** ｜ 星标：**437** ｜ 最近提交：**2026-10-05（很活跃）**
- 形态：一个 Android **库** + 一个 demo App（`app/` 模块），用 Android Studio 打开可直接编译运行

用法（`Mjpeg` 就是它的入口，标准 MJPEG，喂 URL 即可）：

```kotlin
val TIMEOUT = 5 // seconds
Mjpeg.newInstance()
  .open("http://192.168.4.1:81/stream", TIMEOUT)
  .subscribe { inputStream ->
      mjpegView.setSource(inputStream)
      mjpegView.setDisplayMode(DisplayMode.BEST_FIT)
      mjpegView.showFps(true)
  }
```

它内部封装了 SimpleMjpegView / android-camera-axis，支持凭据、快照、旋转镜像。

**优点**：成熟、活跃、协议宽松（MIT，方便自己改）。
**缺点**：要装 Android Studio 编一下，或者在它的 demo 上改。

---

## 4. 方案 4：perthcpe23/android-mjpeg-view（轻量库）

- 仓库：https://github.com/perthcpe23/android-mjpeg-view
- 协议：**MIT** ｜ 星标：**67** ｜ 最近提交：**2026-07-11**
- 形态：纯显示用的自定义 View，Maven Central 有包，也提供 `.aar`

```kotlin
MjpegView(context).apply {
    setUrl("http://192.168.4.1:81/stream")
    mode = MjpegView.MODE_FIT_WIDTH
    supportPinchZoomAndPan = true
    startStream()
}
```

**优点**：最轻，几十行就能拼出一个自己的 App；支持双指缩放。
**缺点**：只是个 View，控制按钮（切风格）要自己加（可以 `/cmd?c=0` 那套接口）。

---

## 5. ⚠️ 注意：GitHub 上多数 "IP Camera" App 是**反方向**的

搜索时会看到很多高分项目，例如：

| 项目 | 实质 | 与我们的关系 |
|---|---|---|
| `DigitallyRefined/android-ip-camera`（→ 衍生 `bartekmotyl/android-ip-camera`） | **把手机变成摄像头**，内置 HTTP 服务输出 MJPEG，给 Frigate / Home Assistant 用 | ❌ 方向相反，我们不需要 |
| `androidok/IP_Cam` | 同上，手机当 IP 摄像头（MJPEG + RTSP） | ❌ 方向相反 |
| `fitri-hy/ipcamera-android` | 同上（CameraX + NanoHTTPD） | ❌ 方向相反 |

这些是"**服务端**"，用来把闲置手机当监控摄像头；我们的场景里**服务端是 ESP32**，
手机是**客户端**。之所以列出来，是为了避免在这些项目上浪费时间。

> 顺带一提：如果我们以后反过来想把手机画面喂给 FPGA，这类项目才是对的工具。

---

## 6. 如果都不满意：自己写一个（工作量很小）

有了 MJPEG `/stream`，一个最小 Android 客户端就是一个 `WebView` 或一个
`MjpegView` + 3 个按钮：

```kotlin
// 风格按钮
fetch("http://192.168.4.1/cmd?c=0")   // 切到风格 0
```

因为控制接口（`/cmd`）和视频流（端口 81）是**分开的端口**，App 可以一边拉流一边发控制命令，
互不阻塞——这也是固件里特意把 MJPEG 放到独立端口 + 独立任务的原因。

---

## 7. 附：各方案对固件的依赖

| 方案 | 需要的固件特性 | 依赖库 |
|---|---|---|
| 内置网页 | `/frame.raw`、`/cmd`、`/status`（默认全开） | 无 |
| VLC | `/stream`（MJPEG） | `esp32-camera` |
| ipcam-view / android-mjpeg-view | `/stream`（MJPEG） | `esp32-camera` |
| 自写 App | 上面全部 | 同上 |

装了 `esp32-camera` 库时 `/stream` 自动启用；不装则端点不注册、其余功能照常，
所以可以先不装库、用内置网页跑通整条链路，再决定要不要装库上原生 App。
