#pragma once
#include "Arduino.h"

#define PIXFORMAT_RGB565 4

typedef struct {
  uint8_t *buf;
  size_t len;
  uint16_t width;
  uint16_t height;
  int format;
  int8_t _shim_pad;
} camera_fb_t;
