#pragma once
#include "Arduino.h"

#define WIFI_AP 2

class IPAddress {
public:
  String toString() const { return String("192.168.4.1"); }
};

struct WifiShim {
  void mode(int) {}
  void setSleep(bool) {}
  bool softAP(const char *, const char *, int, bool, int) { return true; }
  IPAddress softAPIP() const { return IPAddress(); }
};
extern WifiShim WiFi;
