#ifndef IMX219_DRV_H
#define IMX219_DRV_H
#include <stdint.h>

#define IMX219_ADDR     0x10      // 7 位 I2C 地址
#define IMX219_W        1280      // 输出宽（2x2 模拟合并）
#define IMX219_H        962       // 输出高：960 有效 + 2 行余量（FPGA 按 CAM_CTRL.skip 跳过帧首嵌入数据行）
#define IMX219_FLL      1708      // 帧长（合并模式单位 2 行）：182.4MHz / (3560 x 1708) = 30.0fps
#define IMX219_EXP_MAX  (IMX219_FLL - 4)
#define IMX219_AG_MAX   232       // 模拟增益码上限：256/(256-232) = 10.67 倍

int  imx219_init(void);                     // 0 成功；-1 读 ID 失败；-2 ID 不符（应为 0x0219）；-3 配置失败
void imx219_stream(int on);
void imx219_set_exposure(uint32_t lines);   // 单位：1 行时间 = 3560/182.4MHz = 19.52us，范围 1..IMX219_EXP_MAX
void imx219_set_again(uint32_t code);       // 模拟增益 = 256/(256-code)，code 0..232
void imx219_set_dgain(uint32_t g);          // 数字增益 4.8 定点，0x100 = 1 倍，0x100..0xFFF
int  imx219_set_orient(int hv);             // bit0 水平镜像 bit1 垂直翻转（停流写入）；返回新 Bayer 相位
void imx219_test_pattern(int mode);         // 0 关闭；2 彩条；其余见手册 0x0600

#endif
