// 实时风格化视频系统 RISC-V 主程序
//   上电：自检 → 装载网络权重与风格系数 → 摄像头初始化 → 启动 NN 与 IN 逐帧刷新
//   按键：KEY0 切风格  KEY1 切显示模式  KEY2 IN 刷新开/关  KEY3 NN 开/关；挥手左右切风格
//   串口：0-9 风格  n 下一风格  m 显示模式  i IN 刷新  o NN 开/关  s 状态
//         a 自动曝光/白平衡开关  e/E 手动曝光减/增  f 翻转（镜像/倒置循环）  t 彩条测试图  k 帧首跳行 0/2
#include <stdint.h>
#include "hal.h"
#include "vision.h"
#ifndef STYLECAM_CAMERA_SC431HAI
#define STYLECAM_CAMERA_SC431HAI 1
#endif
#if STYLECAM_CAMERA_SC431HAI
#include "sc431hai.h"
#ifndef SC431HAI_BAYER
#define SC431HAI_BAYER 0
#endif
#else
#include "imx219.h"
#include "isp.h"
#endif
#include "net_blob.h"

// 帧首跳过行数：CSI RX 已按数据类型滤掉嵌入数据行时为 0，否则为 2（上板后看画面顶行是否有杂点确定，也可按 k 切换）
#ifndef CAM_SKIP
#define CAM_SKIP 0
#endif

static const char *const mode_name[] = {"SIDE-BY-SIDE", "STYLE FULL", "ORIGINAL FULL"};

// 无浮点的十进制格式化：v 为放大 10 倍的值，输出 "xx.x"
static char *fmt1(char *p, uint32_t v10)
{
    char t[12];
    int n = 0;
    uint32_t ip = v10 / 10;
    do { t[n++] = (char)('0' + ip % 10); ip /= 10; } while (ip);
    while (n) *p++ = t[--n];
    *p++ = '.';
    *p++ = (char)('0' + v10 % 10);
    *p = 0;
    return p;
}

static char *cat(char *p, const char *s)
{
    while (*s) *p++ = *s++;
    *p = 0;
    return p;
}

static void upper(char *d, const char *s, int n)
{
    int i = 0;
    for (; s[i] && i < n - 1; i++) d[i] = (s[i] >= 'a' && s[i] <= 'z') ? (char)(s[i] - 32) : s[i];
    for (; i < n - 1; i++) d[i] = ' ';
    d[n - 1] = 0;
}

static int mode, nn_on = 1;
#if !STYLECAM_CAMERA_SC431HAI
static int tp_on;
#endif

static void draw_labels(void)
{
    char buf[40];
    osd_puts(0, 2, "RISC-V + FPGA REAL-TIME STYLE TRANSFER  (Ti60F225)", 0);
    osd_puts(2, 0, "                                                                                ", 0);
    if (mode == DISP_SIDE) {
        osd_puts(2, 14, "ORIGINAL", 0);
        upper(buf, net_styles[vision_style()], 16);
        osd_puts(2, 50, "STYLE: ", 1);
        osd_puts(2, 57, buf, 1);
    }
    osd_puts(21, 2, "KEY0 STYLE  KEY1 VIEW  KEY2 IN-REFRESH  KEY3 NN ON/OFF", 0);
}

static void draw_status(uint32_t fps10, uint32_t lat10)
{
    char buf[96], *p = buf;
    p = cat(p, "FPS ");
    p = fmt1(p, fps10);
    p = cat(p, "   NN ");
    p = fmt1(p, lat10);
    p = cat(p, " ms   VIEW ");
    p = cat(p, mode_name[mode]);
    p = cat(p, in_refresh_enabled() ? "   IN ON " : "   IN OFF");
    p = cat(p, nn_on ? "        " : "   NN OFF");
    osd_puts(19, 2, "                                                                          ", 0);
    osd_puts(19, 2, buf, 1);
}

static void apply(int style_changed)
{
    vision_set_mode(mode);
    if (style_changed) draw_labels();
}

int main(void)
{
    hal_init();
    hal_puts("\r\nStyleCam boot\r\n");
    if (!STYLECAM_BOARD_CONFIRMED) {
        hal_puts("STOP: confirm sw/board_profile.h against BSP, clocks and DDR linker map\r\n");
        while (1) ;
    }
    if (vision_id() != 0x53544C31u) {
        hal_puts("vision core not found\r\n");
        while (1) ;
    }
    int n = vision_load_blob(net_blob, NET_BLOB_WORDS);
    hal_puts(n > 0 ? "net blob loaded\r\n" : "net blob error\r\n");
    if (n <= 0) {
        vision_enable(0);
        while (1) ;
    }
    if (vision_set_buffer_base(STYLECAM_FRAME_BASE) != 0) {
        hal_puts("STOP: invalid frame buffer base/alignment\r\n");
        while (1) ;
    }
    // IMX219 上电：XCLR 拉低 10ms 后拉高，等待 ≥6.2ms（手册 t4+t5）再访问 I2C
    vision_cam_power(0);
    hal_delay_ms(10);
    vision_cam_power(1);
    hal_delay_ms(10);
#if STYLECAM_CAMERA_SC431HAI
    int cr = sc431hai_init();
    hal_puts(cr == 0 ? "SC431HAI ID/init ok; verify MIPI timing on board\r\n" : "SC431HAI init failed\r\n");
    vision_cam_bayer(SC431HAI_BAYER);
    vision_cam_gains(256, 256, 256);
    vision_cam_ctrl(0, 0, 0);
#else
    int cr = imx219_init();
    hal_puts(cr == 0 ? "IMX219 ok\r\n" : cr == -2 ? "IMX219 ID mismatch\r\n" : "IMX219 init failed\r\n");
    isp_init(CAM_SKIP);
#endif
    if (cr != 0) {
        vision_enable(0);
        while (1) ;
    }

    osd_clear();
    vision_set_style(0);
    in_refresh_enable(1);
    mode = DISP_SIDE;
    apply(1);
    vision_enable(1);

    uint32_t t_last = vision_timer(), f_last = vision_nn_frames(), keys_last = 0;
    uint32_t fps10 = 0;
    while (1) {
        in_refresh_poll();
#if !STYLECAM_CAMERA_SC431HAI
        isp_poll();
#endif

        // 按键（上升沿）
        uint32_t k = hal_keys(), kp = k & ~keys_last;
        keys_last = k;
        int ch = hal_getc();
        int style = vision_style(), sc = 0;
        int g = gesture_poll();               // 挥手：右挥下一个风格，左挥上一个
        if (g) { style = (style + g + NET_NSTYLE) % NET_NSTYLE; sc = 1; }
        if ((kp & 1) || ch == 'n') { style = (style + 1) % NET_NSTYLE; sc = 1; }
        if (ch >= '0' && ch <= '9' && ch - '0' < NET_NSTYLE) { style = ch - '0'; sc = 1; }
        if ((kp & 2) || ch == 'm') { mode = (mode + 1) % 3; sc = 1; }
        if ((kp & 4) || ch == 'i') in_refresh_enable(!in_refresh_enabled());
        if ((kp & 8) || ch == 'o') { nn_on = !nn_on; vision_enable(nn_on); }
#if !STYLECAM_CAMERA_SC431HAI
        if (ch == 'a') { isp_auto(!isp_auto_on()); hal_puts(isp_auto_on() ? "AE/AWB on\r\n" : "AE/AWB off\r\n"); }
        if (ch == 'e') isp_manual_ev(-1);
        if (ch == 'E') isp_manual_ev(1);
        if (ch == 'f') { char b[] = "flip 0\r\n"; b[5] = (char)('0' + isp_flip()); hal_puts(b); }
        if (ch == 't') { tp_on = !tp_on; isp_test_pattern(tp_on); }
        if (ch == 'k') hal_puts(isp_skip_toggle() ? "skip 2\r\n" : "skip 0\r\n");
#endif
        if (sc) {
            if (style != vision_style()) vision_set_style(style);
            apply(1);
        }
        if (kp) hal_delay_ms(20);            // 去抖

        // 每 0.5 s 刷新帧率与延迟
        uint32_t t = vision_timer();
        if (t - t_last >= F_AXI / 2) {
            uint32_t f = vision_nn_frames();
            uint64_t num = (uint64_t)(f - f_last) * F_AXI * 10u;
            fps10 = (uint32_t)(num / (t - t_last));
            uint32_t lat10 = (uint32_t)((uint64_t)vision_nn_cycles() * 10000u / F_AXI);
            draw_status(fps10, lat10);
            t_last = t;
            f_last = f;
            if (ch == 's') {
                char b[160], *p = b;
                p = cat(p, "fps ");
                p = fmt1(p, fps10);
                p = cat(p, "  ");
#if STYLECAM_CAMERA_SC431HAI
                p = cat(p, "SC431HAI fixed exposure/gain; AE/AWB not enabled");
#else
                isp_status(p);
#endif
                while (*p) p++;
                p = cat(p, "\r\n");
                hal_puts(b);
            }
        }
    }
}
