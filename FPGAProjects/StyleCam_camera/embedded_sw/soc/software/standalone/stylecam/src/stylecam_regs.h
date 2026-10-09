/* StyleCam APB3 registers (rtl/sc_apb_regs.v), Sapphire APB slave 0 */
#pragma once
#include <stdint.h>
#include "soc.h"

#define SC_BASE            IO_APB_SLAVE_0_INPUT          /* 0xF8100000 */
#define SC_REG(off)        (*(volatile uint32_t *)(SC_BASE + (off)))

#define SC_ID              SC_REG(0x00)
#define SC_CTRL            SC_REG(0x04)   /* [0] run [1] cam_enable [2] step (pulse) [5:4] style [9:8] view */
#define SC_STATUS          SC_REG(0x08)   /* [7:0] flags, [18:16] sched state, [20:19] req style, [26:25] engine style, [28:27] keys down */
#define SC_IRQ_PEND        SC_REG(0x0C)   /* W1C */
#define SC_IRQ_EN          SC_REG(0x10)
#define SC_I2C_CMD         SC_REG(0x14)   /* [15:0] reg [23:16] data [24] read; write starts */
#define SC_I2C_STAT        SC_REG(0x18)   /* [0] busy [3:1] result [15:8] read data [16] done */
#define SC_CAPTURED        SC_REG(0x20)
#define SC_PROCESSED       SC_REG(0x24)
#define SC_SKIPPED         SC_REG(0x28)
#define SC_CAP_ERRORS      SC_REG(0x2C)
#define SC_SENSOR_FRAMES   SC_REG(0x30)
#define SC_VIDEO_ERRORS    SC_REG(0x34)
#define SC_RUN_CYCLES      SC_REG(0x38)   /* last network pass, 100 MHz cycles */
#define SC_JOB_CYCLES      SC_REG(0x3C)   /* last job (all passes + IN update) */
#define SC_JOB_PASSES      SC_REG(0x40)
#define SC_HDMI_FRAMES     SC_REG(0x44)
#define SC_HDMI_UNDERFLOW  SC_REG(0x48)   /* pixels in the last HDMI frame */
#define SC_HDMI_ERRORS     SC_REG(0x4C)   /* AXI read/write + replay errors */
#define SC_RGB_R           SC_REG(0x50)   /* shadow gain, 16-bit Q8.8 0..65535; zero -> 255 */
#define SC_RGB_G           SC_REG(0x54)
#define SC_RGB_B           SC_REG(0x58)
#define SC_RGB_COMMIT      SC_REG(0x5C)   /* write bit0 to commit; read bit0=pending */
#define SC_CFG_ADDR        SC_REG(0x60)   /* [4:0] layer [27:16] coefficient address */
#define SC_CFG_LO          SC_REG(0x64)
#define SC_CFG_HI          SC_REG(0x68)   /* [5:0] data[37:32]; write commits */
#define SC_OSD(i)          SC_REG(0x2000 + 4 * (i))

/* CTRL */
#define CTRL_RUN           (1u << 0)
#define CTRL_CAM_EN        (1u << 1)
#define CTRL_STEP          (1u << 2)
#define CTRL_STYLE(s)      ((uint32_t)(s) << 4)
#define CTRL_VIEW(v)       ((uint32_t)(v) << 8)
/* STATUS flags */
#define ST_FRAME_READY     (1u << 0)
#define ST_ENGINE_IDLE     (1u << 1)
#define ST_DDR_READY       (1u << 2)
#define ST_STYLES_READY(s) (((s) >> 3) & 7u)
#define ST_CFG_REJECT      (1u << 6)
#define ST_HDMI_UNDERFLOW  (1u << 7)
#define ST_ENGINE_STYLE(s) (((s) >> 25) & 3u)
/* IRQ */
#define IRQ_PUBLISH        (1u << 0)
#define IRQ_KEY3           (1u << 1)
#define IRQ_KEY2           (1u << 2)
#define IRQ_ERROR          (1u << 3)

#define OSD_COLS 80
#define OSD_ROWS 23
#define OSD_HI   0x80          /* highlight colour */

/* Match the reference camera top-level zero-gain fallback. */
static inline unsigned sc_rgb_effective(unsigned gain) { return gain ? gain : 255u; }
