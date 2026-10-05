// IMX219 摄像头驱动（寄存器依据 Sony《IMX219PQH5-C 数据手册》与 Linux 主线 drivers/media/i2c/imx219.c，
// PLL/时序与厂商 piv2_*_2L_reg.mem 一致）
//   I2C：7 位地址 0x10，16 位寄存器地址，8 位数据；INCK 24MHz（模组板载晶振）
//   输出：2 lane、912Mbps/lane（CSI 字节时钟 114MHz）、RAW10；每帧开头 2 行嵌入数据（DT 0x12）
//   模式：2x2 模拟合并，传感器窗口居中 2560x1924（全幅 78%）→ 输出 1280x962；行长 3560（合并模式最小值）；
//         帧长 1708（单位 2 行）→ 30fps；窗口起点为偶数，无翻转时 Bayer 为 RGGB
#include "hal.h"
#include "imx219.h"

typedef struct { uint16_t reg; uint8_t val; } imx_reg_t;

static const imx_reg_t init_tab[] = {
    {0x0100, 0x00},                                 // 软待机
    // 访问 0x3000-0x5FFF 的解锁序列
    {0x30EB, 0x05}, {0x30EB, 0x0C}, {0x300A, 0xFF}, {0x300B, 0xFF}, {0x30EB, 0x05}, {0x30EB, 0x09},
    // 厂商未公开寄存器（主线驱动 imx219_common_regs）
    {0x455E, 0x00}, {0x471E, 0x4B}, {0x4767, 0x0F}, {0x4750, 0x14}, {0x4540, 0x00}, {0x47B4, 0x14},
    {0x4713, 0x30}, {0x478B, 0x10}, {0x478F, 0x10}, {0x4793, 0x10}, {0x4797, 0x0E}, {0x479B, 0x0E},
    {0x0170, 0x01}, {0x0171, 0x01},                 // X/Y 奇数递增 1（不跳读）
    {0x0128, 0x00},                                 // D-PHY 时序自动
    {0x012A, 0x18}, {0x012B, 0x00},                 // INCK = 24MHz
    // PLL（2 lane）：24/3x57 = 456MHz，/5 → 像素时钟 91.2MHz（x2 管线 = 182.4MHz）；24/3x114 = 912Mbps
    {0x0301, 0x05}, {0x0303, 0x01}, {0x0304, 0x03}, {0x0305, 0x03},
    {0x0306, 0x00}, {0x0307, 0x39}, {0x030B, 0x01}, {0x030C, 0x00}, {0x030D, 0x72},
    {0x0114, 0x01},                                 // CSI-2 2 lane
    // 窗口：X 360..2919（2560），Y 270..2193（1924），均为居中且起点为偶数
    {0x0164, 0x01}, {0x0165, 0x68}, {0x0166, 0x0B}, {0x0167, 0x67},
    {0x0168, 0x01}, {0x0169, 0x0E}, {0x016A, 0x08}, {0x016B, 0x91},
    {0x0174, 0x03}, {0x0175, 0x03},                 // 水平/垂直 x2 模拟合并
    {0x016C, 0x05}, {0x016D, 0x00},                 // 输出宽 1280
    {0x016E, 0x03}, {0x016F, 0xC2},                 // 输出高 962
    {0x0624, 0x05}, {0x0625, 0x00}, {0x0626, 0x03}, {0x0627, 0xC2},   // 测试图窗口同输出尺寸
    {0x018C, 0x0A}, {0x018D, 0x0A}, {0x0309, 0x0A}, // RAW10
    {0x0160, 0x06}, {0x0161, 0xAC},                 // 帧长 1708
    {0x0162, 0x0D}, {0x0163, 0xE8},                 // 行长 3560
    {0x0172, 0x00},                                 // 不翻转（RGGB）
    {0x015A, 0x03}, {0x015B, 0xE8},                 // 曝光 1000 行 ≈ 19.5ms
    {0x0157, 0x00},                                 // 模拟增益 1 倍
    {0x0158, 0x01}, {0x0159, 0x00},                 // 数字增益 1 倍
    {0x0600, 0x00}, {0x0601, 0x00},                 // 关闭测试图
    {0xFFFF, 0x00},                                 // 结束标记
};

static int wr(uint16_t reg, uint8_t val) { return hal_i2c_write16(IMX219_ADDR, reg, val); }

static int wr16(uint16_t reg, uint16_t val)
{
    return wr(reg, (uint8_t)(val >> 8)) | wr((uint16_t)(reg + 1), (uint8_t)val);
}

int imx219_init(void)
{
    uint8_t hi, lo;
    if (hal_i2c_read16(IMX219_ADDR, 0x0000, &hi) || hal_i2c_read16(IMX219_ADDR, 0x0001, &lo)) return -1;
    if (hi != 0x02 || lo != 0x19) return -2;           // MODEL_ID = 0x0219
    wr(0x0103, 0x01);                                  // 软复位
    hal_delay_ms(10);
    for (const imx_reg_t *p = init_tab; p->reg != 0xFFFF; p++)
        if (wr(p->reg, p->val)) return -3;
    wr(0x0100, 0x01);                                  // 开流
    return 0;
}

void imx219_stream(int on) { wr(0x0100, on ? 0x01 : 0x00); }

void imx219_set_exposure(uint32_t lines)
{
    if (lines < 1) lines = 1;
    if (lines > IMX219_EXP_MAX) lines = IMX219_EXP_MAX;
    wr16(0x015A, (uint16_t)lines);
}

void imx219_set_again(uint32_t code)
{
    if (code > IMX219_AG_MAX) code = IMX219_AG_MAX;
    wr(0x0157, (uint8_t)code);
}

void imx219_set_dgain(uint32_t g)
{
    if (g < 0x100) g = 0x100;
    if (g > 0xFFF) g = 0xFFF;
    wr16(0x0158, (uint16_t)g);
}

int imx219_set_orient(int hv)
{
    // 流传输中不能改翻转（主线驱动同样在开流期间锁定），停流 → 写 → 开流，丢 1~2 帧
    wr(0x0100, 0x00);
    hal_delay_ms(40);
    wr(0x0172, (uint8_t)(hv & 3));
    wr(0x0100, 0x01);
    return hv & 3;   // 翻转后 Bayer：0 RGGB 1 GRBG 2 GBRG 3 BGGR，与 CAM_BAYER 编码一致
}

void imx219_test_pattern(int mode) { wr16(0x0600, (uint16_t)mode); }
