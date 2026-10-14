/*
 * shim.cpp - the few definitions the host headers only declare, so a real executable
 * can be linked and run on a PC.  Used by tools/check_host.sh (see voice_test.cpp);
 * none of this runs on the device.
 */
#include "Arduino.h"
#include "WiFi.h"
#include "driver/uart.h"

/* The esp32-camera library is optional, so its helper is only defined when its
 * stub header is present - mirroring the two build configurations the sketch supports. */
#if __has_include("img_converters.h")
  #include "img_converters.h"
  #define HOST_STUB_CAMERA 1
#else
  #define HOST_STUB_CAMERA 0
#endif

HostSerial Serial, Serial1, Serial2;
EspShim ESP;
WifiShim WiFi;

void delay(uint32_t) {}
uint32_t millis() { return 0; }

void xTaskCreatePinnedToCore(TaskFn, const char *, uint32_t, void *, uint32_t, void **, int) {}
void vTaskDelay(TickType_t) {}

/* Not exercised on the host: the tests call the matching helpers directly. */
int uart_read_bytes(uart_port_t, uint8_t *, uint32_t, TickType_t) { return 0; }

void *ps_malloc(size_t n) { return calloc(1, n); }
bool psramFound() { return true; }

#if HOST_STUB_CAMERA
bool frame2jpg(camera_fb_t *, uint8_t, uint8_t **, size_t *) { return false; }
#endif
