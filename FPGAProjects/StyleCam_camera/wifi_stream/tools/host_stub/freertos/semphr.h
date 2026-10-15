#pragma once
#include <mutex>
using SemaphoreHandle_t = std::mutex *;
#define portMAX_DELAY 0xffffffffu
inline SemaphoreHandle_t xSemaphoreCreateMutex() { return new std::mutex; }
inline bool xSemaphoreTake(SemaphoreHandle_t mutex, uint32_t) { mutex->lock(); return true; }
inline bool xSemaphoreGive(SemaphoreHandle_t mutex) { mutex->unlock(); return true; }
