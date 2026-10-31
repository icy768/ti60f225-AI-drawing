/*
 * StyleCam phone preview bridge - ESP32-S3-N16R8
 * ----------------------------------------------
 * Receives the 160x120 banded RGB332 (or legacy RGB332/RGB565) preview serialised by Ti60F225 on
 * `stream_tx` (3 Mbaud 8N1), keeps the newest complete frame in PSRAM and serves it over
 * WiFi so a phone can watch the stylised video.
 *
 * Endpoints
 *   GET /            built-in viewer page (no app install, any phone browser)
 *   GET /frame.raw   newest frame, raw RGB565 little endian, X-Width / X-Height / X-Seq headers
 *   GET /frame.bmp   24-bit BMP snapshot of the newest frame
 *   GET /stream      MJPEG on port 81 (only when the esp32-camera library is installed)
 *   GET /status      JSON counters: frames, fps, CRC errors, drops, style, voice events
 *   GET /cmd?c=0     forward one console command to the RISC-V (0/1/2 style, v view, s status)
 *   GET /voice       what the voice module actually sent, so the rule table can be filled in
 *
 * Voice control
 *   The Ai-Thinker VC-02 talks to UART2 (115200 8N1).  It reports one hex frame per
 *   recognised command word and - this matters - those bytes are typed in by hand on
 *   the voice platform, so nothing can be assumed about them.  Each frame is matched
 *   against VOICE_RULES in config.h and mapped onto the RISC-V console commands
 *   0 / 1 / 2 / v / s, which are then forwarded on UART2 TX at 115200. That is the line
 *   the serial console already uses, so no FPGA-side protocol is added.  Unmatched
 *   frames are logged and kept for GET /voice, which is how the table gets filled in.
 *
 * Board settings (Arduino IDE, ESP32 core 3.x)
 *   Board            : ESP32S3 Dev Module
 *   PSRAM            : OPI PSRAM            (required: the frame buffers live in PSRAM)
 *   Flash size       : 16MB (128Mb)
 *   Partition scheme : 16M Flash (3MB APP/9.9MB FATFS) or "Huge APP"
 *   USB CDC On Boot  : Enabled only if you want the log on the native USB port
 *
 * Optional MJPEG
 *   Install the "esp32-camera" library (Library Manager) to enable GET /stream, a
 *   multipart/x-mixed-replace JPEG stream. That is the format third-party open-source
 *   viewers expect (VLC, niqdev/ipcam-view, perthcpe23/android-mjpeg-view). Without the
 *   library the endpoint is simply not registered and the built-in page still works.
 */
#include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>
#include <driver/uart.h>
#include <esp_heap_caps.h>
#include <freertos/semphr.h>

/* esp32-camera is optional: only pulled in when it is actually installed. */
#if __has_include("esp_camera.h")
  #include "esp_camera.h"
  #include "img_converters.h"
  #define STYLECAM_MJPEG 1
#else
  #define STYLECAM_MJPEG 0
#endif

#include "config.h"
#include "web_page.h"
#include "qr_codes.h"

/* ------------------------------------------------------------------ wiring */
/* Everything tunable (SSID, baud rates, preview size, voice debounce) lives in config.h. */
#define PIN_FPGA_RX   18      /* UART1 RX <- FPGA stream_tx                */
#define PIN_FPGA_TX   17      /* UART2 TX -> FPGA uart_rx, 115200 baud     */
#define PIN_VOICE_RX  16      /* UART2 RX <- voice module TX               */
// UART2 receives VC-02 at 115200 and transmits console commands at the same rate.
// VC-02 RX is unused. UART1 receives the independent 3.03 Mbaud video stream only.

/* ------------------------------------------------------------------ frame protocol */
/* Must match sc_stream_link.v: A5 5A | type | seq | w | h | fmt | len_lo len_hi | ... */
#define SYNC0         0xA5
#define SYNC1         0x5A
#define TYPE_VIDEO    0x01

/* ------------------------------------------------------------------ state */
static uint8_t *frameA = nullptr, *frameB = nullptr, *front = nullptr, *back = nullptr;
static volatile uint32_t frameSeq = 0, frameCount = 0, crcErrors = 0, syncLosses = 0;
static volatile uint16_t lastSeq = 0;
static uint32_t fpsWindow = 0, fpsValue = 0;
static volatile char lastVoice = 0;
static volatile uint32_t voiceCount = 0, cmdCount = 0;
/* Voice diagnostics: every burst seen, and how many matched no rule. */
static volatile uint32_t voiceRaw = 0, voiceUnknown = 0;
/* Recording switch shared by every recorder: phone pages poll it, and a PC bridge watching the
 * USB log ("[rec] start" / "[rec] stop") can drive an HDMI capture recorder from it. */
static volatile bool recOn = false;
static volatile uint32_t recEpoch = 0;          /* increments on every start */
static volatile char curStyle = '0';            /* last style command sent to the FPGA */
/* Style blend sent to the FPGA as "b T A" (blend toward style T by A/8); a style command clears it. */
static volatile uint8_t blendTo = 1, blendA = 0;
static volatile uint8_t viewers = 0;            /* open port-82 push streams */
static const uint32_t frameW = PREVIEW_W, frameH = PREVIEW_H;
static SemaphoreHandle_t frameMutex;

static WebServer server(80);          /* control + snapshots + built-in page        */
#if STYLECAM_MJPEG
static WebServer cam(81);             /* MJPEG only, runs in its own task           */
#endif

/* ------------------------------------------------------------------ CRC16-CCITT (0x1021 / 0xFFFF) */
static uint16_t crcStep(uint16_t c, uint8_t b) {
  c ^= (uint16_t)b << 8;
  for (int i = 0; i < 8; i++) c = (c & 0x8000) ? (uint16_t)((c << 1) ^ 0x1021) : (uint16_t)(c << 1);
  return c;
}

static void setRecording(bool on, const char *source) {
  if (on == recOn) return;
  if (on) recEpoch++;
  recOn = on;
  Serial.printf("[rec] %s style=%c source=%s\n", on ? "start" : "stop", curStyle, source);
}

static void forwardCommand(char c) {
  /* 'r' / 'R' start / stop recording; they stay on the ESP32 and never reach the FPGA. */
  if (c == 'r' || c == 'R') { setRecording(c == 'r', "command"); return; }
  if (c >= '0' && c <= '2') { curStyle = c; blendA = 0; }    /* the firmware clears the blend too */
  Serial2.write((uint8_t)c);
  Serial2.flush();
  cmdCount++;
  Serial.printf("[cmd] -> FPGA console: '%c'\n", c);
}

/* ------------------------------------------------------------------ UART1 frame parser */
static uint8_t chunk[4096];
static uint8_t bandBuf[PREVIEW_W * PREVIEW_H / PREVIEW_BANDS];   /* one banded packet, RGB332 */

static inline uint16_t rgb332to565(uint8_t b) {
  uint8_t r = b >> 5, g = (b >> 2) & 7, blue = b & 3;
  return ((r << 2 | r >> 1) << 11) | ((g << 3 | g) << 5) | (blue << 3 | blue << 1 | blue >> 1);
}

/* Frame layout produced by sc_stream_link.v (CRC covers the sync pair onwards):
 *   A5 5A | type | seq | w | h | fmt | len_lo | len_hi | payload... | crc_lo crc_hi */
static void consumeFpgaByte(uint8_t b) {
  static enum { S_SYNC0, S_SYNC1, S_HEADER, S_PAYLOAD, S_CRC } st = S_SYNC0;
  static uint8_t hdr[7];       /* type seq w h fmt len_lo len_hi */
  static int hi = 0;
  static uint16_t len = 0, got = 0, crc = 0xFFFF;
  static uint8_t crcLo = 0;
  static bool haveLo = false;

      switch (st) {
        case S_SYNC0:
          if (b == SYNC0) st = S_SYNC1;
          break;

        case S_SYNC1:
          if (b == SYNC1) {
            st = S_HEADER; hi = 0;
            crc = crcStep(0xFFFF, SYNC0);
            crc = crcStep(crc, SYNC1);
          } else if (b != SYNC0) {
            st = S_SYNC0; syncLosses++;
          }
          break;

        case S_HEADER:
          hdr[hi++] = b;
          crc = crcStep(crc, b);
          if (hi == 7) {
            uint16_t bytes = (uint16_t)hdr[5] | ((uint16_t)hdr[6] << 8);
            /* geometry is fixed at compile time: a different length means we are not
             * aligned on a real frame, so resync instead of trusting the header. */
            bool banded = (hdr[4] & 0xFC) == 0x20 && (hdr[4] & 3) < PREVIEW_BANDS;
            uint32_t want = banded ? PREVIEW_W * PREVIEW_H / PREVIEW_BANDS
                                   : PREVIEW_W * PREVIEW_H * (hdr[4] == 0 ? 2 : 1);
            if (hdr[0] != TYPE_VIDEO || hdr[2] != PREVIEW_W || hdr[3] != PREVIEW_H ||
                (hdr[4] > 1 && !banded) || bytes != want) {
              crcErrors++; st = S_SYNC0; break;
            }
            len = bytes;
            got = 0;
            st = S_PAYLOAD;          /* the same byte is fully consumed here */
          }
          break;

        case S_PAYLOAD:
          if (hdr[4] >= 0x20) {
            bandBuf[got] = b;        /* rows are placed only after the CRC passes */
          } else if (hdr[4] == 1) {
            // Expand RGB332 to the existing RGB565 snapshot/HTTP/JPEG layout.
            uint16_t rgb = rgb332to565(b);
            back[2 * got] = uint8_t(rgb);
            back[2 * got + 1] = uint8_t(rgb >> 8);
          } else {
            back[got] = b;
          }
          got++;
          crc = crcStep(crc, b);
          if (got >= len) { st = S_CRC; haveLo = false; }
          break;

        case S_CRC:
          if (!haveLo) { crcLo = b; haveLo = true; }
          else {
            uint16_t want = (uint16_t)crcLo | ((uint16_t)b << 8);
            if (want == crc && got == len && hdr[4] >= 0x20) {
              /* Banded: assemble the rows in the back buffer and publish only when all bands
               * of one cycle arrived, so a lost band never leaves stale rows on the phone. */
              static uint32_t bandMask = 0;
              uint32_t band = hdr[4] & 3, i = 0;
              if (band == 0) bandMask = 0;
              for (uint32_t y = band; y < PREVIEW_H; y += PREVIEW_BANDS) {
                uint8_t *row = back + 2 * y * PREVIEW_W;
                for (uint32_t x = 0; x < PREVIEW_W; x++, i++) {
                  uint16_t rgb = rgb332to565(bandBuf[i]);
                  row[2 * x] = uint8_t(rgb);
                  row[2 * x + 1] = uint8_t(rgb >> 8);
                }
              }
              bandMask |= 1u << band;
              if (band == PREVIEW_BANDS - 1 && bandMask == (1u << PREVIEW_BANDS) - 1) {
                xSemaphoreTake(frameMutex, portMAX_DELAY);
                uint8_t *t = front; front = back; back = t;
                frameCount++;
                lastSeq = hdr[1];
                frameSeq = lastSeq;
                xSemaphoreGive(frameMutex);
                bandMask = 0;
              }
            } else if (want == crc && got == len) {
              xSemaphoreTake(frameMutex, portMAX_DELAY);
              uint8_t *t = front; front = back; back = t;
              frameCount++;
              lastSeq = hdr[1];
              frameSeq = lastSeq;
              xSemaphoreGive(frameMutex);
            } else {
              crcErrors++;
            }
            st = S_SYNC0;
          }
          break;
      }
}

static void readFpgaTask(void *) {
  for (;;) {
    int n = uart_read_bytes(UART_NUM_1, chunk, sizeof(chunk), pdMS_TO_TICKS(20));
    for (int i = 0; i < n; i++) consumeFpgaByte(chunk[i]);
  }
}

// Readers copy a complete published frame while the receiver owns the other buffer.
// Network writes and JPEG conversion happen after releasing the mutex.
static bool copyFrame(uint8_t *dst, uint32_t *seq) {
  xSemaphoreTake(frameMutex, portMAX_DELAY);
  bool ready = frameCount != 0;
  if (ready) { memcpy(dst, front, PREVIEW_BYTES); *seq = frameSeq; }
  xSemaphoreGive(frameMutex);
  return ready;
}

/* ------------------------------------------------------------------ HTTP handlers */
static void handleRoot() {
  server.sendHeader("Cache-Control", "no-store");
  server.send_P(200, "text/html; charset=utf-8", INDEX_HTML);
}

/* RGB565 little endian -> RGB332, exact for the preview (it is RGB332 on the wire).
 * May run in place: byte i is written after bytes 2i, 2i+1 were read. */
static void to332(const uint8_t *src, uint8_t *dst, size_t pixels) {
  for (size_t i = 0; i < pixels; i++) {
    uint16_t v = src[2 * i] | (src[2 * i + 1] << 8);
    dst[i] = ((v >> 13) << 5) | (((v >> 8) & 7) << 2) | ((v >> 3) & 3);
  }
}

/* GET /frame.raw[?fmt=332][&after=<seq>]
 * fmt=332 sends one RGB332 byte per pixel (exact: the preview is RGB332 on the wire), half
 * the bytes of RGB565.  after=<seq> answers 204 at once when no newer frame exists, so the
 * viewer only moves pixels when there is something new to show. */
static void handleFrameRaw() {
  bool p332 = server.arg("fmt") == "332";
  if (server.hasArg("after") && frameCount != 0 && (uint32_t)server.arg("after").toInt() == frameSeq) {
    server.send(204, "text/plain", "");
    return;
  }
  uint8_t *snapshot = (uint8_t *)ps_malloc(PREVIEW_BYTES);
  if (!snapshot) { server.send(500, "text/plain", "oom"); return; }
  uint32_t seq;
  if (!copyFrame(snapshot, &seq)) { free(snapshot); server.send(503, "text/plain", "no frame yet"); return; }
  size_t n = PREVIEW_BYTES;
  if (p332) {
    to332(snapshot, snapshot, PREVIEW_W * PREVIEW_H);
    n = PREVIEW_W * PREVIEW_H;
  }
  server.sendHeader("X-Width", String(frameW));
  server.sendHeader("X-Height", String(frameH));
  server.sendHeader("X-Seq", String(seq));
  server.sendHeader("X-Format", p332 ? "rgb332" : "rgb565le");
  server.setContentLength(n);
  server.send(200, "application/octet-stream", "");
  WiFiClient c = server.client();
  c.write(snapshot, n);
  free(snapshot);
}

static void handleFrameBmp() {
  uint8_t *snapshot = (uint8_t *)ps_malloc(PREVIEW_BYTES);
  if (!snapshot) { server.send(500, "text/plain", "oom"); return; }
  uint32_t seq;
  if (!copyFrame(snapshot, &seq)) { free(snapshot); server.send(503, "text/plain", "no frame yet"); return; }
  const uint32_t rowRaw = frameW * 2;
  const uint32_t pad = (4 - (frameW * 3) % 4) % 4;
  const uint32_t rowOut = frameW * 3 + pad;
  const uint32_t pixels = rowOut * frameH;
  const uint32_t size = 54 + pixels;
  uint8_t *bmp = (uint8_t *)ps_malloc(size);
  if (!bmp) { free(snapshot); server.send(500, "text/plain", "oom"); return; }
  memset(bmp, 0, 54);
  bmp[0] = 'B'; bmp[1] = 'M';
  memcpy(bmp + 2, &size, 4);
  uint32_t off = 54; memcpy(bmp + 10, &off, 4);
  uint32_t dib = 40; memcpy(bmp + 14, &dib, 4);
  int32_t w = frameW, h = frameH;
  memcpy(bmp + 18, &w, 4); memcpy(bmp + 22, &h, 4);
  uint16_t planes = 1, bpp = 24;
  memcpy(bmp + 26, &planes, 2); memcpy(bmp + 28, &bpp, 2);
  memcpy(bmp + 34, &pixels, 4);
  for (uint32_t y = 0; y < frameH; y++) {
    uint8_t *dst = bmp + 54 + (frameH - 1 - y) * rowOut;
    const uint8_t *src = snapshot + y * rowRaw;
    for (uint32_t x = 0; x < frameW; x++) {
      uint16_t v = src[2 * x] | ((uint16_t)src[2 * x + 1] << 8);
      uint8_t r = (v >> 11) & 0x1F, g = (v >> 5) & 0x3F, bl = v & 0x1F;
      dst[3 * x + 0] = (bl << 3) | (bl >> 2);
      dst[3 * x + 1] = (g << 2) | (g >> 4);
      dst[3 * x + 2] = (r << 3) | (r >> 2);
    }
  }
  server.sendHeader("Cache-Control", "no-store");
  server.send_P(200, "image/bmp", (const char *)bmp, size);
  free(snapshot);
  free(bmp);
}

/* GET http://<ap>:RAW_STREAM_PORT/  push stream for the built-in viewer: one response that never
 * ends, each frame "A5 5A seq 00" + W*H RGB332 bytes, sent as soon as a complete frame is
 * published.  One connection instead of a request per frame removes the TCP setup and the empty
 * polls that held the page to ~7 fps.  Own task, so it cannot block the port-80 control API.
 * Up to AP_MAX_CONN viewers (audience phones) share one snapshot per frame; one more viewer
 * replaces the oldest connection, which is usually a reloaded page whose old socket lingers. */
static WiFiServer rawServer(RAW_STREAM_PORT);

static void rawStreamTask(void *) {
  const size_t n = 4 + PREVIEW_W * PREVIEW_H;
  uint8_t *snapshot = (uint8_t *)ps_malloc(PREVIEW_BYTES);
  uint8_t *packet = (uint8_t *)ps_malloc(n);
  if (!snapshot || !packet) { Serial.println("raw stream: PSRAM allocation failed"); vTaskDelete(nullptr); }
  WiFiClient cl[AP_MAX_CONN];
  uint32_t since[AP_MAX_CONN] = {0};
  uint32_t last = 0xFFFFFFFFu;
  for (;;) {
    WiFiClient c = rawServer.accept();
    if (c) {
      c.setTimeout(1);
      for (uint32_t t0 = millis(); c.connected() && millis() - t0 < 1000;)   /* skip the request */
        if (c.readStringUntil('\n').length() <= 1) break;
      c.setNoDelay(true);
      c.print("HTTP/1.1 200 OK\r\nContent-Type: application/octet-stream\r\nCache-Control: no-store\r\n"
              "Access-Control-Allow-Origin: *\r\nConnection: close\r\n\r\n");
      int slot = 0;                                   /* a free slot, else the oldest viewer */
      for (int i = 0; i < AP_MAX_CONN; i++) {
        if (!cl[i].connected()) { slot = i; break; }
        if (since[i] < since[slot]) slot = i;
      }
      cl[slot].stop(); cl[slot] = c; since[slot] = millis();
      Serial.printf("[view] viewer joined slot %d\n", slot);
    }
    uint8_t live = 0;
    for (int i = 0; i < AP_MAX_CONN; i++) if (cl[i].connected()) live++;
    viewers = live;
    uint32_t seq;
    if (!live || !copyFrame(snapshot, &seq) || seq == last) { vTaskDelay(pdMS_TO_TICKS(live ? 3 : 20)); continue; }
    last = seq;
    packet[0] = SYNC0; packet[1] = SYNC1; packet[2] = uint8_t(seq); packet[3] = 0;
    to332(snapshot, packet + 4, PREVIEW_W * PREVIEW_H);
    for (int i = 0; i < AP_MAX_CONN; i++)
      if (cl[i].connected() && cl[i].write(packet, n) != n) cl[i].stop();
  }
}

#if STYLECAM_MJPEG
/* MJPEG: one JPEG per preview frame, pushed as multipart/x-mixed-replace so generic
 * viewers keep the connection open and repaint on every part. Encoding runs on the
 * snapshot of the published frame, without holding the UART buffer across network I/O. */
static void handleStream() {
  WiFiClient c = cam.client();
  uint8_t *snapshot = (uint8_t *)ps_malloc(PREVIEW_BYTES);
  if (!snapshot) { cam.send(500, "text/plain", "oom"); return; }
  c.print("HTTP/1.0 200 OK\r\nContent-Type: multipart/x-mixed-replace; boundary=stylecambound\r\n"
          "Cache-Control: no-store\r\nConnection: close\r\n\r\n");
  uint32_t lastSeq = 0xFFFFFFFFu;
  uint32_t lastMs = 0;
  while (c.connected()) {
    uint32_t seq;
    if (!copyFrame(snapshot, &seq) || seq == lastSeq) { delay(5); continue; }
    lastSeq = seq;
    // esp32-camera expects RGB565 big endian; the FPGA wire format is little endian.
    for (size_t i = 0; i < PREVIEW_BYTES; i += 2) {
      uint8_t lo = snapshot[i]; snapshot[i] = snapshot[i + 1]; snapshot[i + 1] = lo;
    }
    camera_fb_t fb;
    memset(&fb, 0, sizeof(fb));
    fb.buf = snapshot;
    fb.len = PREVIEW_BYTES;
    fb.width = frameW;
    fb.height = frameH;
    fb.format = PIXFORMAT_RGB565;
    uint8_t *jpg = nullptr;
    size_t jl = 0;
    if (!frame2jpg(&fb, 80, &jpg, &jl) || !jl) { delay(10); continue; }
    c.printf("--stylecambound\r\nContent-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n",
             (unsigned)jl);
    c.write(jpg, jl);
    c.print("\r\n");
    free(jpg);
    uint32_t now = millis();
    if (now - lastMs < 33) delay(33 - (now - lastMs));   /* ~30 fps ceiling */
    lastMs = millis();
  }
  free(snapshot);
}

/* Own task so a viewer holding the stream open cannot starve the port-80 control API. */
static void streamTask(void *) {
  for (;;) {
    cam.handleClient();
    vTaskDelay(pdMS_TO_TICKS(2));
  }
}
#endif

static void handleStatus() {
  char buf[448];
  snprintf(buf, sizeof(buf),
           "{\"frames\":%lu,\"fps\":%lu,\"seq\":%u,\"w\":%lu,\"h\":%lu,"
           "\"crc_errors\":%lu,\"sync_losses\":%lu,\"commands\":%lu,\"voice\":%lu,\"last_voice\":%d,"
           "\"voice_raw\":%lu,\"voice_unknown\":%lu,"
           "\"heap\":%lu,\"psram\":%lu,\"rec\":%d,\"rec_epoch\":%lu,\"style\":%d,"
           "\"blend_to\":%u,\"blend_a\":%u,\"viewers\":%u}",
           (unsigned long)frameCount, (unsigned long)fpsValue, (unsigned)frameSeq,
           (unsigned long)frameW, (unsigned long)frameH,
           (unsigned long)crcErrors, (unsigned long)syncLosses, (unsigned long)cmdCount,
           (unsigned long)voiceCount, (int)lastVoice,
           (unsigned long)voiceRaw, (unsigned long)voiceUnknown,
           (unsigned long)ESP.getFreeHeap(), (unsigned long)ESP.getFreePsram(),
           recOn ? 1 : 0, (unsigned long)recEpoch, curStyle - '0',
           (unsigned)blendTo, (unsigned)blendA, (unsigned)viewers);
  server.send(200, "application/json", buf);
}

/* GET /rec?on=1|0 : the phone REC button. */
static void handleRec() {
  if (server.hasArg("on")) setRecording(server.arg("on") == "1", "phone");
  char buf[64];
  snprintf(buf, sizeof(buf), "{\"rec\":%d,\"rec_epoch\":%lu}", recOn ? 1 : 0, (unsigned long)recEpoch);
  server.send(200, "application/json", buf);
}

/* GET /blend?to=T&a=A : mix the current style toward style T by A/8 (A = 0 turns it off). */
static void handleBlend() {
  int to = server.hasArg("to") ? server.arg("to").toInt() : blendTo;
  int a = server.hasArg("a") ? server.arg("a").toInt() : 0;
  if (to < 0 || to > 2 || a < 0 || a > 8) { server.send(400, "text/plain", "bad blend"); return; }
  blendTo = to; blendA = a;
  const uint8_t msg[3] = {'b', uint8_t('0' + to), uint8_t('0' + a)};
  Serial2.write(msg, 3);
  Serial2.flush();
  cmdCount++;
  Serial.printf("[blend] style %c -> %d, %d/8\n", curStyle, to, a);
  char buf[48];
  snprintf(buf, sizeof(buf), "{\"blend_to\":%d,\"blend_a\":%d}", to, a);
  server.send(200, "application/json", buf);
}

static void handleQr(const char *svg) {
  server.sendHeader("Cache-Control", "max-age=86400");
  server.send_P(200, "image/svg+xml", svg);
}

static void handleCmd() {
  if (!server.hasArg("c") || server.arg("c").length() == 0) { server.send(400, "text/plain", "missing c"); return; }
  char c = server.arg("c")[0];
  if (strchr("012vzswht", c) == nullptr) { server.send(400, "text/plain", "bad c"); return; }
  forwardCommand(c);
  server.send(200, "application/json", "{\"ok\":true}");
}

/* ------------------------------------------------------------------ UART2 voice bridge */
/*
 * The VC-02 reports one short hex frame per command word, and those bytes are typed in
 * by hand on the voice platform - so this deliberately is not a fixed parser.  A frame
 * is delimited by an inter-byte gap, matched against VOICE_RULES, and every frame is
 * remembered so it can be read back from GET /voice and pasted into config.h.
 */
#if VOICE_MODE == VOICE_MODE_FRAME

static uint8_t  vHist[VOICE_CAPTURE_DEPTH][VOICE_BURST_MAX];
static volatile uint8_t vHistLen[VOICE_CAPTURE_DEPTH];
static volatile uint32_t vHistHead = 0;
static char vLastPat[4 * VOICE_BURST_MAX] = "";

static int hexNib(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  return -1;
}

/* Render bytes the way they are written in VOICE_RULES: "A1 00 01 01 FF". */
static void fmtBurst(char *dst, int cap, const uint8_t *b, int n) {
  int p = 0;
  for (int i = 0; i < n && p < cap - 3; i++)
    p += snprintf(dst + p, (size_t)(cap - p), i ? " %02X" : "%02X", b[i]);
  dst[p] = 0;
}

/* "A1 00 ?? FF" -> {0xA1, 0x00, 0x100, 0xFF}.  Token count, or 0 for a malformed rule. */
static int patParse(const char *pat, uint16_t *out) {
  int n = 0;
  while (*pat && n < VOICE_BURST_MAX) {
    while (*pat == ' ' || *pat == '\t') pat++;
    if (!*pat) break;
    if (pat[0] == '?' && pat[1] == '?') { out[n++] = 0x100; pat += 2; continue; }
    int hi = hexNib(pat[0]), lo = hexNib(pat[1]);
    if (hi < 0 || lo < 0) return 0;
    out[n++] = (uint16_t)((hi << 4) | lo);
    pat += 2;
  }
  return n;
}

/* Match against an arbitrary rule table so the host self-test can feed its own.
 * A rule only fires on an exact token-count match: a truncated or padded burst must
 * not be mistaken for a hit, which is also why leading junk never matches. */
static char ruleMatchIn(const voiceRule_t *rules, unsigned count, const uint8_t *b, int n) {
  for (unsigned r = 0; r < count; r++) {
    uint16_t pat[VOICE_BURST_MAX];
    int pn = patParse(rules[r].pat, pat);
    if (pn <= 0 || pn != n) continue;
    bool hit = true;
    for (int i = 0; i < pn; i++)
      if (pat[i] != 0x100 && pat[i] != b[i]) { hit = false; break; }
    if (hit) return rules[r].cmd;
  }
  return 0;
}

static char ruleMatch(const uint8_t *b, int n) {
  return ruleMatchIn(VOICE_RULES, (unsigned)VOICE_RULE_COUNT, b, n);
}

/* A frame is whatever arrives back to back; the first silent gap ends it. */
static bool burstDone(int n, uint32_t now, uint32_t lastByte) {
  return n > 0 && (now - lastByte >= VOICE_GAP_MS || n >= VOICE_BURST_MAX);
}

/* Runs from the voice task only. */
static void voiceHandleBurst(const uint8_t *b, int n, uint32_t now) {
  static uint32_t lastMs = 0;
  static char lastCmd = 0;
  char pat[4 * VOICE_BURST_MAX];

  voiceRaw++;
  fmtBurst(pat, sizeof(pat), b, n);

  uint32_t slot = vHistHead % VOICE_CAPTURE_DEPTH;
  memcpy(vHist[slot], b, (size_t)n);
  vHistLen[slot] = (uint8_t)n;
  vHistHead++;

  char cmd = ruleMatch(b, n);
  if (!cmd) {
    voiceUnknown++;
    Serial.printf("[voice] unmatched: %s   <- put this in VOICE_RULES (config.h)\n", pat);
    return;
  }
  /* Debounce a repeat of the SAME command only - a different word said right after
   * the previous one must still get through. */
  if (cmd == lastCmd && now - lastMs < VOICE_DEBOUNCE_MS) return;
  lastMs = now;
  lastCmd = cmd;

  strncpy(vLastPat, pat, sizeof(vLastPat) - 1);
  vLastPat[sizeof(vLastPat) - 1] = 0;
  lastVoice = cmd; voiceCount++;
  Serial.printf("[voice] %s -> console '%c'\n", pat, cmd);
  forwardCommand(cmd);
}

static void readVoiceTask(void *) {
  uint8_t burst[VOICE_BURST_MAX];
  int n = 0;
  uint32_t lastByte = 0;
  for (;;) {
    uint32_t now = millis();
    if (burstDone(n, now, lastByte)) {
      voiceHandleBurst(burst, n, now);
      n = 0;
    }
    int got = uart_read_bytes(UART_NUM_2, burst + n, (uint32_t)(VOICE_BURST_MAX - n), pdMS_TO_TICKS(5));
    if (got > 0) { n += got; lastByte = millis(); }
  }
}

/* GET /voice - the bench tool: shows what the module really sends, newest first. */
static void handleVoice() {
  static char buf[1536];
  int p = snprintf(buf, sizeof(buf),
                   "{\"mode\":%d,\"rules\":%u,\"bursts\":%lu,\"unknown\":%lu,\"last\":\"%s\",\"captured\":[",
                   VOICE_MODE, (unsigned)VOICE_RULE_COUNT,
                   (unsigned long)voiceRaw, (unsigned long)voiceUnknown, vLastPat);
  noInterrupts();
  uint32_t head = vHistHead;
  interrupts();
  for (uint32_t i = 0; i < VOICE_CAPTURE_DEPTH && p < (int)sizeof(buf) - 96; i++) {
    uint32_t idx = head > i ? head - 1 - i : 0;
    char pat[4 * VOICE_BURST_MAX];
    noInterrupts();
    int len = vHistLen[idx];
    uint8_t copy[VOICE_BURST_MAX];
    memcpy(copy, vHist[idx], (size_t)len);
    interrupts();
    fmtBurst(pat, sizeof(pat), copy, len);
    p += snprintf(buf + p, sizeof(buf) - p, "%s\"%s\"", i ? "," : "", pat);
  }
  snprintf(buf + p, sizeof(buf) - p, "]}");
  server.sendHeader("Cache-Control", "no-store");
  server.send(200, "application/json", buf);
}

#else  /* VOICE_MODE == VOICE_MODE_CHAR */

static char voiceMapChar(char c) {
  if (c == VOICE_STYLE_1) return '0';                             /* style 0 (VAN GOGH) */
  if (c == VOICE_STYLE_2) return '1';                             /* style 1 (UKIYO-E)  */
  if (c == VOICE_STYLE_3) return '2';                             /* style 2 (INK WASH) */
  if (c == VOICE_LAYOUT || c == 'v' || c == 'V') return 'v';      /* cycle layout       */
  if (c == VOICE_STATUS || c == 's' || c == 'S') return 's';      /* print status       */
  return 0;
}

static void readVoiceTask(void *) {
  uint8_t b;
  uint32_t lastMs = 0;
  for (;;) {
    if (uart_read_bytes(UART_NUM_2, &b, 1, pdMS_TO_TICKS(50)) <= 0) continue;
    voiceRaw++;
    char mapped = voiceMapChar((char)b);
    if (!mapped) {
      voiceUnknown++;
      Serial.printf("[voice] ignored 0x%02X\n", b);
      continue;
    }
    uint32_t now = millis();
    if (now - lastMs < VOICE_DEBOUNCE_MS) continue;               /* debounce repeats   */
    lastMs = now;
    lastVoice = mapped; voiceCount++;
    Serial.printf("[voice] '%c' -> console '%c'\n", (char)b, mapped);
    forwardCommand(mapped);
  }
}

static void handleVoice() {
  static char buf[192];
  snprintf(buf, sizeof(buf), "{\"mode\":%d,\"bursts\":%lu,\"unknown\":%lu,\"last\":\"%c\"}",
           VOICE_MODE, (unsigned long)voiceRaw, (unsigned long)voiceUnknown,
           lastVoice ? (char)lastVoice : '?');
  server.sendHeader("Cache-Control", "no-store");
  server.send(200, "application/json", buf);
}

#endif

/* ------------------------------------------------------------------ stats ticker */
static void statsTask(void *) {
  for (;;) {
    vTaskDelay(pdMS_TO_TICKS(1000));
    uint32_t f = frameCount;
    fpsValue = f - fpsWindow;
    fpsWindow = f;
    Serial.printf("[link] frames=%lu fps=%lu crcErr=%lu syncLoss=%lu cmds=%lu voice=%lu heap=%lu psram=%lu\n",
                  (unsigned long)f, (unsigned long)fpsValue, (unsigned long)crcErrors,
                  (unsigned long)syncLosses, (unsigned long)cmdCount, (unsigned long)voiceCount,
                  (unsigned long)ESP.getFreeHeap(), (unsigned long)ESP.getFreePsram());
  }
}

/* ------------------------------------------------------------------ setup */
void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println("\n=== StyleCam phone preview bridge (ESP32-S3-N16R8) ===");

  if (!psramFound()) {
    Serial.println("FATAL: PSRAM not found. Set Tools -> PSRAM -> OPI PSRAM.");
    while (true) delay(1000);
  }
  frameA = (uint8_t *)ps_malloc(PREVIEW_BYTES);
  frameB = (uint8_t *)ps_malloc(PREVIEW_BYTES);
  if (!frameA || !frameB) { Serial.println("FATAL: PSRAM allocation failed"); while (true) delay(1000); }
  memset(frameA, 0, PREVIEW_BYTES);
  memset(frameB, 0, PREVIEW_BYTES);
  front = frameA; back = frameB;
  frameMutex = xSemaphoreCreateMutex();
  if (!frameMutex) { Serial.println("FATAL: mutex allocation failed"); while (true) delay(1000); }

  Serial1.setRxBufferSize(32768);
  Serial1.begin(FPGA_BAUD, SERIAL_8N1, PIN_FPGA_RX, -1);
  /* Interrupt at 64 of the 128 hardware FIFO bytes: ~210 us of slack at 3 Mbaud instead of
   * ~27 us with the default threshold, so Wi-Fi interrupt load does not overrun the FIFO. */
  Serial1.setRxFIFOFull(64);
  Serial2.begin(VOICE_BAUD, SERIAL_8N1, PIN_VOICE_RX, PIN_FPGA_TX);
#if VOICE_MODE == VOICE_MODE_FRAME
  Serial.printf("Voice: VC-02 frame mode, %u rules at %d baud - open /voice while you speak\n",
                (unsigned)VOICE_RULE_COUNT, VOICE_BAUD);
#else
  Serial.printf("Voice: single-character mode at %d baud\n", VOICE_BAUD);
#endif

  WiFi.mode(WIFI_AP);
  WiFi.softAP(AP_SSID, AP_PASSWORD, AP_CHANNEL, false, AP_MAX_CONN);
  WiFi.setSleep(false);
  Serial.printf("AP \"%s\" ready - open http://%s/ on the phone\n", AP_SSID, WiFi.softAPIP().toString().c_str());

  server.on("/", handleRoot);
  server.on("/frame.raw", handleFrameRaw);
  server.on("/frame.bmp", handleFrameBmp);
  server.on("/status", handleStatus);
  server.on("/cmd", handleCmd);
  server.on("/voice", handleVoice);
  server.on("/rec", handleRec);
  server.on("/blend", handleBlend);
  server.on("/qr/wifi.svg", []() { handleQr(QR_WIFI_SVG); });
  server.on("/qr/url.svg", []() { handleQr(QR_URL_SVG); });
  server.onNotFound([]() { server.send(404, "text/plain", "not found"); });
  server.begin();
  rawServer.begin();
  rawServer.setNoDelay(true);
  Serial.printf("Viewer push stream: http://%s:%d/\n", WiFi.softAPIP().toString().c_str(), RAW_STREAM_PORT);

#if STYLECAM_MJPEG
  cam.on("/stream", handleStream);
  cam.onNotFound([]() { cam.send(404, "text/plain", "not found"); });
  cam.begin();
  Serial.printf("MJPEG: http://%s:81/stream (open in VLC or an MJPEG viewer app)\n",
                WiFi.softAPIP().toString().c_str());
#else
  Serial.println("MJPEG disabled (install the 'esp32-camera' library to enable port 81 /stream)");
#endif

  xTaskCreatePinnedToCore(readFpgaTask, "fpga_rx", 4096, nullptr, 6, nullptr, 1);
  xTaskCreatePinnedToCore(readVoiceTask, "voice", 3072, nullptr, 3, nullptr, 1);
  xTaskCreatePinnedToCore(statsTask, "stats", 3072, nullptr, 1, nullptr, 0);
  xTaskCreatePinnedToCore(rawStreamTask, "raw_stream", 4096, nullptr, 2, nullptr, 0);
#if STYLECAM_MJPEG
  xTaskCreatePinnedToCore(streamTask, "mjpeg", 4096, nullptr, 2, nullptr, 0);
#endif
}

void loop() {
  server.handleClient();
  vTaskDelay(pdMS_TO_TICKS(1));
}
