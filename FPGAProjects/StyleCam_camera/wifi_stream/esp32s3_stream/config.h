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
/* UART1 talks to the FPGA `stream_tx` line (3.03 Mbaud, matches DIV=33 @100 MHz). */
#define FPGA_BAUD     3000000
/* UART2 talks to the offline voice module; most modules default to 9600 8N1. */
#define VOICE_BAUD    9600
/* Ignore repeated recognitions arriving within this window (milliseconds). */
#define VOICE_DEBOUNCE_MS 300

/* ---------------------------------------------------------------- preview */
/* Must match sc_stream_tap.v / sc_stream_link.v on the FPGA side. */
#define PREVIEW_W     96
#define PREVIEW_H     54
#define PREVIEW_BYTES (PREVIEW_W * PREVIEW_H * 2)

/* ---------------------------------------------------------------- serial log */
#define LOG_BAUD      115200

/* ---------------------------------------------------------------- voice map */
/* Single characters the offline module is expected to emit on recognition.
 * They are translated to the RISC-V serial-console commands the FPGA already
 * understands (see stylecam/src/main.c): 0/1/2 = style, v = layout, s = status. */
#define VOICE_STYLE_1 '1'   /* -> console '0' */
#define VOICE_STYLE_2 '2'   /* -> console '1' */
#define VOICE_STYLE_3 '3'   /* -> console '2' */
#define VOICE_LAYOUT  'V'   /* -> console 'v' */
#define VOICE_STATUS  'S'   /* -> console 's' */
