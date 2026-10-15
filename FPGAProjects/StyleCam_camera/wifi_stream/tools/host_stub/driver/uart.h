#pragma once
#include "Arduino.h"

typedef int uart_port_t;
#define UART_NUM_1 1
#define UART_NUM_2 2

int uart_read_bytes(uart_port_t, uint8_t *, uint32_t, TickType_t);
