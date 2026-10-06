// HAL 的 Sapphire SoC 实现（函数与宏名已按厂商 hardjtag 工程生成的 BSP 核对：
//   soc.h：SYSTEM_UART_0_IO_CTRL / SYSTEM_I2C_0_IO_CTRL / SYSTEM_GPIO_0_IO_CTRL / SYSTEM_CLINT_HZ，
//          IO_APB_SLAVE_0_INPUT = 0xf8100000（视觉子系统寄存器基址）
//   i2c.h：i2c_applyConfig / i2c_writeData_w / i2c_readData_w（16 位寄存器地址，slaveAddr 为 8 位写地址）
//   uart.h：uart_write / uart_read / uart_readOccupancy；gpio.h：gpio_getInput；bsp.h：bsp_uDelay）
#include "bsp.h"
#include "soc.h"
#include "uart.h"
#include "gpio.h"
#include "i2c.h"
#include "hal.h"

#define HAL_UART   BSP_UART_TERMINAL
#define HAL_GPIO   SYSTEM_GPIO_0_IO_CTRL      // 按键接 GPIO0[3:0]（低有效）
#define HAL_I2C    SYSTEM_I2C_0_IO_CTRL       // 摄像头 SCCB
#define I2C_HZ     SYSTEM_CLINT_HZ
#define I2C_FREQ   100000                     // 100kHz（手册标准模式）

void hal_init(void)
{
    I2c_Config c;
    c.samplingClockDivider = 3;
    c.timeout = I2C_HZ / 10;
    c.tsuDat  = I2C_HZ / I2C_FREQ / 3;
    c.tLow    = I2C_HZ / I2C_FREQ / 2;
    c.tHigh   = I2C_HZ / I2C_FREQ / 2;
    c.tBuf    = I2C_HZ / I2C_FREQ;
    i2c_applyConfig(HAL_I2C, &c);
}

void hal_putc(char c) { uart_write(HAL_UART, c); }

void hal_puts(const char *s) { while (*s) hal_putc(*s++); }

int hal_getc(void)
{
    if (uart_readOccupancy(HAL_UART) == 0) return -1;
    return uart_read(HAL_UART);
}

uint32_t hal_keys(void) { return (~gpio_getInput(HAL_GPIO)) & 0xF; }

void hal_delay_ms(uint32_t ms) { bsp_uDelay(ms * 1000); }

int hal_i2c_write16(uint8_t dev7, uint16_t reg, uint8_t val)
{
    i2c_writeData_w(HAL_I2C, (u8)(dev7 << 1), reg, &val, 1);
    return 0;
}

int hal_i2c_read16(uint8_t dev7, uint16_t reg, uint8_t *val)
{
    i2c_readData_w(HAL_I2C, (u8)(dev7 << 1), reg, val, 1);
    return 0;
}
