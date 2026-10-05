// 摄像头自动曝光 / 自动白平衡（IMX219 无片上 ISP，由 RISC-V 按 FPGA 帧统计闭环控制）
#ifndef ISP_H
#define ISP_H
#include <stdint.h>

void isp_init(int skip);             // 前端寄存器与初始曝光（imx219_init 之后调用）；skip：帧首跳过行数 0/2
int  isp_poll(void);                 // 有新统计帧时执行一步 AE/AWB，返回 1
void isp_auto(int on);               // AE + AWB 开关
int  isp_auto_on(void);
void isp_manual_ev(int dir);         // 手动曝光量 ×9/8 或 ×7/8（自动关闭）
int  isp_flip(void);                 // 翻转循环 0→1→2→3（bit0 水平 bit1 垂直），同步 Bayer 相位，返回新值
void isp_test_pattern(int on);       // 传感器彩条，前端切直通（黑电平 0、增益 1、gamma 关），冻结 AE/AWB
int  isp_skip_toggle(void);          // 帧首跳过行数 0 ↔ 2（CSI RX 未滤嵌入数据行时画面顶行为杂点，切到 2）
void isp_status(char *buf);          // "Y 115 EXP 1536 AG 37 DG 256 WB 440/273/420 AUTO"（buf ≥ 80 字节）

#endif
