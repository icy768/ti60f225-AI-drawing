#pragma once
#include "Arduino.h"

class WiFiClient {
public:
  bool connected() { return true; }
  size_t write(const uint8_t *, size_t) { return 0; }
  size_t write(const char *) { return 0; }
  void printf(const char *, ...) {}
  void print(const char *) {}
};

class WebServer {
public:
  WebServer(int) {}
  typedef void (*Handler)();
  void on(const char *, Handler) {}
  void onNotFound(Handler) {}
  void begin() {}
  void handleClient() {}
  WiFiClient client() { return WiFiClient(); }
  void send(int, const char *, const char *) {}
  void send(int, const char *, const String &) {}
  void send_P(int, const char *, const char *) {}
  void send_P(int, const char *, const char *, size_t) {}
  void sendHeader(const char *, const String &) {}
  void setContentLength(size_t) {}
  bool hasArg(const char *) { return true; }
  String arg(const char *) { return String(); }
};
