#ifndef SC431HAI_H
#define SC431HAI_H
#include <stdint.h>

int  sc431hai_init(void);                          // 0 成功；-1 I2C 失败；-2 ID 不符；-3 配置失败
void sc431hai_stream(int on);
void sc431hai_set_exposure(uint32_t half_rows);
void sc431hai_set_again(uint8_t coarse, uint8_t fine);

#endif
