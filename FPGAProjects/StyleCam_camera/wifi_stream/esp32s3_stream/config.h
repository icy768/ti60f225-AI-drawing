/*
 * config.h - StyleCam phone-preview bridge configuration (ESP32-S3-N16R8)
 *
 * Everything a user normally wants to change lives here. The SoftAP credentials are
 * deliberately in the source tree because the phone has to join this network with no
 * other infrastructure present on the demo table; change them before a public demo.
 */
#pragma once

/* ---------------------------------------------------------------- SoftAP */
/* The phone joins this network directly, so no router is needed at the booth. */
#define AP_SSID       "StyleCam"
#define AP_PASSWORD   "stylecam1234"   /* >= 8 chars, or "" for an open AP      */
#define AP_CHANNEL    6                /* 1..13, keep away from the HDMI spot   */
#define AP_MAX_CONN   4

/* ---------------------------------------------------------------- UART */
/* UART1 talks to the FPGA `stream_tx` line: DIV=33 @100 MHz = 3.0303 Mbaud.  Ask for
 * the exact rate - requesting 3000000 lands ~1% off, which eats most of the UART
 * sampling margin at this speed. */
#define FPGA_BAUD     3030303
/* UART2 receives voice on GPIO16 and transmits to FPGA console RX on GPIO17.
 * Both directions use 115200 8N1. VC-02 RX is not wired in this bridge.
 * VC-02's user data port defaults to 115200 8N1
 * (set in the Ai-Thinker voice platform - see the voice section below). */
#define VOICE_BAUD    115200

/* ---------------------------------------------------------------- preview */
/* Must match sc_stream_tap.v / sc_stream_link.v on the FPGA side. */
#define PREVIEW_W     96
#define PREVIEW_H     54
#define PREVIEW_BYTES (PREVIEW_W * PREVIEW_H * 2)

/* ---------------------------------------------------------------- serial log */
#define LOG_BAUD      115200

/* ---------------------------------------------------------------- voice module */
/*
 * The demo uses an Ai-Thinker VC-02 (VC-02-Kit): fully offline recognition on a
 * US516P6, configured on the Ai-Thinker voice platform, http://voice.ai-thinker.com/
 *
 * Two properties of the VC-02 drive everything in this section:
 *
 *  1. UART1 is the user data port, and both its pins and its baud rate are chosen in
 *     the platform.  The vendor walk-through uses 115200 8N1 with B6 = UART1_RX and
 *     B7 = UART1_TX, so that is what VOICE_BAUD assumes.  Do not enable a second
 *     UART1 in the platform or UART1 stops working.
 *
 *  2. The bytes sent for a command word are NOT fixed by the firmware - you type them
 *     yourself, per command, in the platform's "控制详情 -> 串口数据" field.  There is
 *     therefore no such thing as "the" VC-02 protocol to hardcode.  The platform's
 *     default template is five bytes:
 *
 *         [0] 0xA1 start   [1] device position   [2] device type   [3] on/off   [4] 0xFF end
 *
 *     The table below follows that shape, but treat it as a starting point: capture
 *     what your module really sends first (speak a word and read the "[voice]" line
 *     on the USB serial port, or open GET /voice in a browser) and paste those bytes
 *     in here.  That workflow is written up in docs/voice_vc02.md.
 */

/* 1 = match the hex frames below (VC-02, the default)
 * 2 = treat every byte as one ASCII character, for modules that just print text */
#ifndef VOICE_MODE
  #define VOICE_MODE 1
#endif
#define VOICE_MODE_FRAME 1
#define VOICE_MODE_CHAR  2

/* VC-02 sends a whole frame back to back, so a silent gap marks the end of one. */
#define VOICE_GAP_MS       20
/* Ignore a repeat of the same action arriving within this window (milliseconds). */
#define VOICE_DEBOUNCE_MS  300
/* Longest frame we will assemble, and how many past frames GET /voice remembers. */
#define VOICE_BURST_MAX    16
#define VOICE_CAPTURE_DEPTH 8

/* Frame rules.  'pat' is space separated hex, where "??" matches any byte; 'cmd' is
 * the serial-console command forwarded to the FPGA.  The console already implements
 * (stylecam/src/main.c):  '0' '1' '2' = style, 'v' = layout, 's' = status,
 * 'w' = reload weights.
 *
 *                                   ^^^ EDIT THESE TWO COLUMNS TO MATCH YOUR MODULE ^^^
 */
typedef struct { const char *pat; char cmd; } voiceRule_t;

static const voiceRule_t VOICE_RULES[] = {
  { "A1 00 01 01 FF", '0' },   /* "梵高风格" -> style 0  VAN GOGH */
  { "A1 00 02 01 FF", '1' },   /* "浮世绘"   -> style 1  UKIYO-E  */
  { "A1 00 03 01 FF", '2' },   /* "水墨画"   -> style 2  INK WASH */
  { "A1 00 04 01 FF", 'v' },   /* "切换画面" -> cycle the layout  */
  { "A1 00 05 01 FF", 's' },   /* "当前状态" -> print status      */
};
#define VOICE_RULE_COUNT (sizeof(VOICE_RULES) / sizeof(VOICE_RULES[0]))

/* VOICE_MODE 2 only: characters the module prints, and what they mean.  They are
 * translated to the same console commands as above. */
#define VOICE_STYLE_1 '1'   /* -> console '0' */
#define VOICE_STYLE_2 '2'   /* -> console '1' */
#define VOICE_STYLE_3 '3'   /* -> console '2' */
#define VOICE_LAYOUT  'V'   /* -> console 'v' */
#define VOICE_STATUS  'S'   /* -> console 's' */
