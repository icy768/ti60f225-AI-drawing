/*
 * Arduino.h - minimal host stubs so the ESP32-S3 sketch can be type-checked with g++
 * on a PC (no ESP32 toolchain required). It only declares the API surface the sketch
 * touches; nothing here runs on the device. Compile with tools/check_host.sh.
 */
#pragma once
#include <cstdint>
#include <cstddef>
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <string>

#define PROGMEM
#define SERIAL_8N1 0x800001c
#define pdMS_TO_TICKS(x) (x)

typedef uint32_t TickType_t;

/* ---- logging + timing ---- */
struct HostSerial {
  unsigned long baud = 0;
  int rxPin = -1, txPin = -1;
  uint8_t lastByte = 0;
  size_t writes = 0;
  void begin(unsigned long rate) { baud = rate; }
  void setRxBufferSize(size_t) {}
  void begin(unsigned long rate, uint32_t, int rx, int tx) { baud = rate; rxPin = rx; txPin = tx; }
  size_t write(uint8_t b) { lastByte = b; writes++; return 1; }
  void flush() {}
  void println(const char *) {}
  void print(const char *) {}
  void printf(const char *, ...) {}
};
extern HostSerial Serial, Serial1, Serial2;

void delay(uint32_t);
uint32_t millis();

/* ---- critical section (the sketch guards its tiny voice-capture buffer with these) ---- */
inline void noInterrupts() {}
inline void interrupts() {}

/* ---- FreeRTOS shim ---- */
typedef void (*TaskFn)(void *);
void xTaskCreatePinnedToCore(TaskFn, const char *, uint32_t, void *, uint32_t, void **, int);
void vTaskDelay(TickType_t);

/* ---- heap ---- */
void *ps_malloc(size_t);
bool psramFound();
struct EspShim {
  uint32_t getFreeHeap() { return 0; }
  uint32_t getFreePsram() { return 0; }
};
extern EspShim ESP;

/* ---- String ---- */
class String {
public:
  String() {}
  String(const char *s) { snprintf(b_, sizeof(b_), "%s", s ? s : ""); }
  String(uint32_t v) { snprintf(b_, sizeof(b_), "%u", (unsigned)v); }
  unsigned length() const { return (unsigned)strlen(b_); }
  char operator[](unsigned i) const { return b_[i]; }
  const char *c_str() const { return b_; }
private:
  char b_[24] = {0};
};
