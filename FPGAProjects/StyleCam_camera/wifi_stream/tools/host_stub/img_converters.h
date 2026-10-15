#pragma once
#include "esp_camera.h"

/* esp32-camera's JPEG helper: convert a raw frame buffer to JPEG, *out is malloc'd. */
bool frame2jpg(camera_fb_t *fb, uint8_t quality, uint8_t **out, size_t *out_len);
