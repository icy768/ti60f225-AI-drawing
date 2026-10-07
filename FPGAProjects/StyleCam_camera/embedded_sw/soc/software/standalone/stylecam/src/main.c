/*
 * StyleCam RISC-V control firmware (Sapphire RV32I, 16 KB on-chip RAM)
 *
 * - SC431HAI 初始化：通过 APB 下发 I2C 寄存器命令，时序与表格同原 RTL 状态机（rtl/sc431hai/sc_sequence.vh）
 * - 加速器调度：每帧由 CPU 下发单步启动，帧发布中断里统计帧率并下发下一帧
 * - 风格部署：开机依次触发三种风格的 IN 校准作业（13 遍），之后切换风格无需等待
 * - 交互：KEY3 / 串口 0 1 2 切风格，KEY2 / 串口 v 切画面布局；OSD 叠加 FPS、风格、耗时
 */
#include <stdint.h>
#include "bsp.h"
#include "plic.h"
#include "clint.h"
#include "riscv.h"
#include "uart.h"
#include "stylecam_regs.h"
#include "sc431hai_seq.h"

void trap_entry();
void main();

static const char *const STYLE_NAME[3] = {"VAN GOGH", "UKIYO-E", "INK WASH"};
static const char *const VIEW_NAME[3] = {"ORIGINAL | STYLIZED", "STYLIZED FULL", "ORIGINAL FULL"};

static volatile uint32_t ctrl;           /* CTRL 影子（不含 STEP） */
static volatile uint32_t streaming;      /* 1: 发布中断里自动下发下一帧 */
static volatile uint32_t frames;         /* 已发布帧数 */
static volatile uint32_t key3_count, key2_count, error_count;
static volatile uint32_t switch_pending, switch_style, switch_t0, switch_us_last, switch_us_max;
static volatile uint32_t osd_dirty;

static inline uint32_t now(void) { return (uint32_t)clint_getTime(BSP_CLINT); }       /* 100 MHz */
static inline uint32_t us_since(uint32_t t0) { return (now() - t0) / (BSP_CLINT_HZ / 1000000); }
static void delay_ms(uint32_t ms) { while (ms--) bsp_uDelay(1000); }

static void ctrl_write(uint32_t v) { ctrl = v; SC_CTRL = v; }
static void step_frame(void) { SC_CTRL = ctrl | CTRL_STEP; }
static uint32_t cur_style(void) { return (ctrl >> 4) & 3; }
static uint32_t cur_view(void) { return (ctrl >> 8) & 3; }

/* ---------------- OSD ---------------- */
/* 每行先在缓冲里拼好（0 = 透明），再整行一次写出，避免先清后画造成闪烁 */
static uint8_t rb[OSD_COLS];
static void row_begin(void) { for (int c = 0; c < OSD_COLS; c++) rb[c] = 0; }
static void row_put(int col, const char *s, int hi)
{
    for (; *s && col < OSD_COLS; s++, col++) rb[col] = (uint8_t)*s | (hi ? OSD_HI : 0);
}
static int slen(const char *s) { int n = 0; while (s[n]) n++; return n; }
static void row_center(int center, const char *s, int hi) { row_put(center - slen(s) / 2, s, hi); }
static void row_flush(int row) { for (int c = 0; c < OSD_COLS; c++) SC_OSD(row * OSD_COLS + c) = rb[c]; }
static void osd_clear_all(void) { row_begin(); for (int r = 0; r < OSD_ROWS; r++) row_flush(r); }

/* 无除法器：小整数格式化 */
static char *fmt_u(char *p, uint32_t v)
{
    char t[10]; int n = 0;
    do { t[n++] = '0' + v % 10; v /= 10; } while (v);
    while (n) *p++ = t[--n];
    *p = 0;
    return p;
}
static char *fmt_x10(char *p, uint32_t v)   /* 153 -> "15.3" */
{
    p = fmt_u(p, v / 10);
    *p++ = '.'; *p++ = '0' + v % 10; *p = 0;
    return p;
}
static char *cat(char *p, const char *s) { while (*s) *p++ = *s++; *p = 0; return p; }

static uint32_t fps_x10, cam_fps_x10, nn_ms_x10;

static void osd_draw(void)
{
    char line[OSD_COLS + 1], *p;
    uint32_t view = cur_view(), style = cur_style();
    row_begin();
    row_put(1, "StyleCam  RISC-V + FPGA", 1);
    p = cat(line, "FPS "); fmt_x10(p, fps_x10);
    row_put(64, line, 1);
    row_flush(0);
    row_begin();
    if (view == 0) {
        row_center(20, "ORIGINAL", 0);
        p = cat(line, "STYLIZED - "); cat(p, STYLE_NAME[style]);
        row_center(60, line, 0);
    }
    row_flush(2);
    row_begin();
    p = cat(line, "STYLE "); p = cat(p, STYLE_NAME[style]);
    p = cat(p, "   NN "); p = fmt_x10(p, nn_ms_x10); p = cat(p, " ms   CAM "); p = fmt_x10(p, cam_fps_x10);
    p = cat(p, " fps   VIEW "); cat(p, VIEW_NAME[view]);
    row_put(1, line, 0);
    row_flush(20);
    row_begin();
    row_put(1, "KEY3 / UART 0 1 2 : STYLE      KEY2 / UART v : VIEW", 0);
    row_flush(21);
}

static void osd_message(const char *msg)
{
    row_begin(); row_put(1, msg, 1); row_flush(20);
}

/* ---------------- 中断 ---------------- */
static void on_irq(uint32_t pend)
{
    if (pend & IRQ_PUBLISH) {
        frames++;
        if (switch_pending && ST_ENGINE_STYLE(SC_STATUS) == switch_style) {
            uint32_t us = us_since(switch_t0);
            switch_us_last = us;
            if (us > switch_us_max) switch_us_max = us;
            switch_pending = 0;
        }
        if (streaming) step_frame();          /* 启动下一帧 */
    }
    if (pend & IRQ_KEY3) {
        key3_count++;
        uint32_t s = cur_style() == 2 ? 0 : cur_style() + 1;
        ctrl_write((ctrl & ~CTRL_STYLE(3)) | CTRL_STYLE(s));
        switch_style = s; switch_t0 = now(); switch_pending = 1;
        osd_dirty = 1;
    }
    if (pend & IRQ_KEY2) {
        key2_count++;
        uint32_t v = cur_view() == 2 ? 0 : cur_view() + 1;
        ctrl_write((ctrl & ~CTRL_VIEW(3)) | CTRL_VIEW(v));
        osd_dirty = 1;
    }
    if (pend & IRQ_ERROR) {
        error_count++;
        if (streaming) step_frame();          /* 出错帧已释放，继续 */
    }
}

void trap()
{
    int32_t mcause = csr_read(mcause);
    if (mcause < 0 && (mcause & 0xF) == CAUSE_MACHINE_EXTERNAL) {
        uint32_t claim;
        while ((claim = plic_claim(BSP_PLIC, BSP_PLIC_CPU_0))) {
            if (claim == SYSTEM_PLIC_USER_INTERRUPT_A_INTERRUPT) {
                uint32_t pend;
                while ((pend = SC_IRQ_PEND)) { SC_IRQ_PEND = pend; on_irq(pend); }
            }
            plic_release(BSP_PLIC, BSP_PLIC_CPU_0, claim);
        }
    } else {
        bsp_printf("\r\n*** TRAP mcause=%x mepc=%x ***\r\n", mcause, csr_read(mepc));
        while (1);
    }
}

static void irq_init(void)
{
    SC_IRQ_PEND = 0xF;
    SC_IRQ_EN = IRQ_PUBLISH | IRQ_KEY3 | IRQ_KEY2 | IRQ_ERROR;
    plic_set_threshold(BSP_PLIC, BSP_PLIC_CPU_0, 0);
    plic_set_enable(BSP_PLIC, BSP_PLIC_CPU_0, SYSTEM_PLIC_USER_INTERRUPT_A_INTERRUPT, 1);
    plic_set_priority(BSP_PLIC, SYSTEM_PLIC_USER_INTERRUPT_A_INTERRUPT, 1);
    csr_write(mtvec, trap_entry);
    csr_set(mie, MIE_MEIE);
    csr_write(mstatus, csr_read(mstatus) | MSTATUS_MPP | MSTATUS_MIE);
}

/* ---------------- SC431HAI 驱动 ---------------- */
/* 返回 1 成功，2 NACK，4 超时 */
static int i2c_xfer(uint16_t reg, uint8_t wdata, int read, uint8_t *rdata)
{
    SC_I2C_CMD = (uint32_t)reg | ((uint32_t)wdata << 16) | (read ? (1u << 24) : 0);
    uint32_t t0 = now(), st;
    do {
        st = SC_I2C_STAT;
        if (us_since(t0) > 50000) return 4;
    } while ((st & 1) || !(st & (1u << 16)));
    if (rdata) *rdata = (st >> 8) & 0xFF;
    return (st >> 1) & 7;
}

static uint8_t sensor_diag[9];

/* 0 成功；否则 {错误码<<8 | 命令序号} */
static uint32_t camera_init(void)
{
    ctrl_write(ctrl & ~CTRL_CAM_EN);
    delay_ms(10);
    ctrl_write(ctrl | CTRL_CAM_EN);          /* 传感器上电/解除复位 */
    delay_ms(100);
    for (uint32_t i = 0; i < SC_SEQ_LEN; i++) {
        uint32_t w = sc_seq[i], op = w >> 24, reg = (w >> 8) & 0xFFFF, val = w & 0xFF;
        if (op == 2) {
            if (reg >= 1000) osd_message("SENSOR STREAM ON - SETTLING");
            delay_ms(reg);
            continue;
        }
        int diag = op == 3 && i >= SC_DIAG_FIRST_INDEX;
        if (op == 3 && !diag) return (4u << 8) | i;
        uint8_t rd = 0;
        int r = i2c_xfer(reg, val, op == 1 || diag, &rd);
        if (r != 1) return ((uint32_t)r << 8) | i;
        if (op == 1 && rd != val) return (3u << 8) | i;
        if (diag) sensor_diag[i - SC_DIAG_FIRST_INDEX] = rd;
        delay_ms(1);                          /* STOP-START 间隔 */
    }
    return 0;
}

/* ---------------- 控制台 ---------------- */
static void print_x10(uint32_t v) { bsp_printf("%d.%d", v / 10, v % 10); }

static void print_status(uint32_t t_ms)
{
    uint32_t st = SC_STATUS;
    bsp_printf("[%d ms] fps=", t_ms); print_x10(fps_x10);
    bsp_printf(" cam="); print_x10(cam_fps_x10);
    bsp_printf(" nn_ms="); print_x10(nn_ms_x10);
    bsp_printf(" style=%d view=%d ready=%d proc=%d cap=%d skip=%d caperr=%d vid_err=%d uf=%d hdmi_err=%d irq_err=%d k3=%d k2=%d sw_us=%d sw_max_us=%d\r\n",
               cur_style(), cur_view(), ST_STYLES_READY(st), SC_PROCESSED, SC_CAPTURED, SC_SKIPPED, SC_CAP_ERRORS,
               SC_VIDEO_ERRORS, SC_HDMI_UNDERFLOW, SC_HDMI_ERRORS, error_count, key3_count, key2_count,
               switch_us_last, switch_us_max);
}

static void console(void)
{
    while (uart_readOccupancy(BSP_UART_TERMINAL)) {
        char c = uart_read(BSP_UART_TERMINAL);
        csr_clear(mstatus, MSTATUS_MIE);
        if (c >= '0' && c <= '2') {
            uint32_t s = c - '0';
            if (s != cur_style()) {
                ctrl_write((ctrl & ~CTRL_STYLE(3)) | CTRL_STYLE(s));
                switch_style = s; switch_t0 = now(); switch_pending = 1;
            }
            osd_dirty = 1;
        } else if (c == 'v') {
            uint32_t v = cur_view() == 2 ? 0 : cur_view() + 1;
            ctrl_write((ctrl & ~CTRL_VIEW(3)) | CTRL_VIEW(v));
            osd_dirty = 1;
        }
        csr_set(mstatus, MSTATUS_MIE);
        if (c == 's') print_status(0);
        if (c == 'h' || c == '?') bsp_printf("commands: 0 1 2 style, v view, s status\r\n");
    }
}

/* 等待一帧发布（轮询计数），超时返回 0 */
static int wait_frame(uint32_t before, uint32_t timeout_ms)
{
    uint32_t t0 = now();
    while (frames == before)
        if (us_since(t0) > timeout_ms * 1000) return 0;
    return 1;
}

void main()
{
    bsp_init();
    bsp_printf("\r\nStyleCam RISC-V control  ID=%x  (SC431HAI -> V21b 13-layer CNN -> HDMI)\r\n", SC_ID);
    ctrl_write(CTRL_STYLE(0) | CTRL_VIEW(0));
    osd_clear_all();
    osd_draw();
    osd_message("WAITING FOR DDR CALIBRATION");
    uint32_t t0 = now();
    while (!(SC_STATUS & ST_DDR_READY))
        if (us_since(t0) > 2000000) { bsp_printf("DDR calibration timeout\r\n"); osd_message("DDR CALIBRATION FAILED"); while (1); }
    irq_init();

    osd_message("CONFIGURING SC431HAI OVER I2C");
    uint32_t err = camera_init();
    if (err) {
        char line[40], *p = cat(line, "CAMERA INIT ERROR ");
        p = fmt_u(p, err >> 8); p = cat(p, " AT STEP "); fmt_u(p, err & 0xFF);
        osd_message(line);
        bsp_printf("SC431HAI init failed: code %d at step %d\r\n", err >> 8, err & 0xFF);
        while (1);
    }
    bsp_printf("SC431HAI ready, %d commands; 3e00..3e02=%x %x %x 320e/f=%x %x\r\n", SC_SEQ_LEN,
               sensor_diag[0], sensor_diag[1], sensor_diag[2], sensor_diag[3], sensor_diag[4]);

    /* 风格部署：三种风格各跑一次 IN 校准作业 */
    for (uint32_t s = 0; s < 3; s++) {
        char line[48], *p = cat(line, "DEPLOYING STYLE ");
        p = cat(p, STYLE_NAME[s]); cat(p, " (IN CALIBRATION)");
        osd_message(line);
        ctrl_write((ctrl & ~CTRL_STYLE(3)) | CTRL_STYLE(s));
        uint32_t before = frames, t1 = now();
        step_frame();
        if (!wait_frame(before, 5000)) {
            bsp_printf("style %d calibration timeout, status %x\r\n", s, SC_STATUS);
            osd_message("STYLE CALIBRATION TIMEOUT");
            while (1);
        }
        bsp_printf("style %d (%s) deployed: %d passes, %d us, ready=%d\r\n", s, STYLE_NAME[s], SC_JOB_PASSES,
                   us_since(t1), ST_STYLES_READY(SC_STATUS));
    }

    /* 实时运行：每帧由发布中断启动下一帧 */
    ctrl_write((ctrl & ~CTRL_STYLE(3)) | CTRL_STYLE(0));
    csr_clear(mstatus, MSTATUS_MIE);
    streaming = 1;
    step_frame();
    csr_set(mstatus, MSTATUS_MIE);
    osd_draw();
    bsp_printf("streaming; commands: 0 1 2 style, v view, s status\r\n");

    uint32_t t_last = now(), f_last = frames, s_last = SC_SENSOR_FRAMES, uptime_ms = 0, ticks = 0;
    while (1) {
        console();
        if (osd_dirty) { osd_dirty = 0; osd_draw(); }
        uint32_t dt = us_since(t_last);
        if (dt >= 1000000) {
            uint32_t f = frames, s = SC_SENSOR_FRAMES;
            fps_x10 = (f - f_last) * 10000000u / dt;
            cam_fps_x10 = (s - s_last) * 10000000u / dt;
            nn_ms_x10 = SC_JOB_CYCLES / 10000;          /* 100 MHz 周期 -> 0.1 ms */
            f_last = f; s_last = s; t_last = now(); uptime_ms += dt / 1000;
            osd_draw();
            if (++ticks % 2 == 0) print_status(uptime_ms);
        }
    }
}
