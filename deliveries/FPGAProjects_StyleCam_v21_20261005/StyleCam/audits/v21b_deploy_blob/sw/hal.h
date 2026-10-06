// 板级抽象层：把 Sapphire BSP 的调用集中在 hal_sapphire.c，其余代码与 BSP 无关
#ifndef HAL_H
#define HAL_H
#include <stdint.h>

// 视觉子系统 APB 基址：取 Sapphire IP 生成的 soc.h 中 APB 用户从口 0 的地址宏
#ifndef VISION_BASE
#define VISION_BASE   0xF8100000u   // 占位值，按工程生成的 soc.h 修改
#endif
// AXI 时钟频率（TIMER 寄存器计数频率），用于帧率与延迟换算
#ifndef F_AXI
#define F_AXI         150000000u
#endif

void     hal_init(void);
void     hal_putc(char c);
void     hal_puts(const char *s);
int      hal_getc(void);                     // 无数据返回 -1
uint32_t hal_keys(void);                     // bit0..3 对应 KEY0..3，1 = 按下
int      hal_i2c_write16(uint8_t dev7, uint16_t reg, uint8_t val);   // 0 成功
int      hal_i2c_read16(uint8_t dev7, uint16_t reg, uint8_t *val);
void     hal_delay_ms(uint32_t ms);

#endif
