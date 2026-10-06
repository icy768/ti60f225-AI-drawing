// 摄像头自动曝光 / 自动白平衡（全整数运算）
//   统计：vision_core 在每个摄像头帧写入 DDR 时累加 640x480 的 R/G/B（sRGB 8 位）与过曝像素数
//   AE：曝光量 ev = 曝光行数 x 总增益(x256)。平均亮度 Y=(R+2G+B)/4 向 Y_TARGET 收敛：
//       比值 r = 目标/当前，sRGB 近似 gamma 2 → 线性比 ≈ r²，每步走一半并限制在 0.5~2 倍，±5% 死区；
//       过曝像素 >4% 时不再加亮，>8% 时每步至少压 5%（4%~8% 为保持带，避免来回跳；画面中的灯等小面积高光不影响），
//       >50% 时每步降到 1/4；
//       拆分：先加曝光到上限，再加模拟增益（≤10.67 倍），最后数字增益（≤2 倍）；
//       曝光 ≥10ms 时取 10ms 整数倍（50Hz 电网灯光 100Hz 闪烁，避免横条），余量交给增益；
//       曝光写入后第 2 帧才反映到统计，更新后跳过 2 帧
//   AWB：灰度世界，R、B 增益使其均值向 G 对齐（G 增益固定），每步走 1/4、限 ±10%，±2.3% 死区，
//        仅在 Y 位于 30~200 时更新
#include "hal.h"
#include "vision.h"
#include "imx219.h"
#include "isp.h"

#define NPIX        (640u * 480u)
#define Y_TARGET    115u          // 目标平均亮度（sRGB 8 位）
#define BLK         64u           // IMX219 黑电平（RAW10，手册固定 64）
#define GG          273u          // G 增益固定：256 x 1023/(1023-64)，补足扣黑电平后的满量程
#define GR0         440u          // R/B 初值（约 5000K）
#define GB0         420u
#define WB_MIN      200u
#define WB_MAX      1200u
#define LINE_10MS   512u          // 10ms 对应行数（1 行 19.52us）
#define AG_X256_MAX 2730u         // 模拟增益上限 65536/(256-232)
#define DG_MAX      0x200u        // 数字增益上限 2 倍（4.8 定点）
#define EV_MIN      256u          // 1 行 x 1 倍
#define EV_MAX      ((uint32_t)IMX219_EXP_MAX * AG_X256_MAX * 2u)
#define EV0         (1000u * 256u)

static int auto_on = 1, tp_on, orient, skip_rows;
static uint32_t ev = EV0, gr = GR0, gb = GB0;
static uint32_t cur_lines, cur_code = 0xFFFF, cur_dg;
static uint32_t last_seq, hold, y16_last;

// 曝光量 → 曝光行数 / 模拟增益码 / 数字增益，仅写有变化的寄存器
static void apply_ev(void)
{
    uint32_t lines, g, code, a, dg;
    if (ev <= (uint32_t)IMX219_EXP_MAX * 256u) {
        lines = ev >> 8;
        if (lines >= LINE_10MS) lines -= lines % LINE_10MS;
        if (lines < 1) lines = 1;
    } else {
        lines = IMX219_EXP_MAX - IMX219_EXP_MAX % LINE_10MS;      // 1536 行 = 30ms
    }
    g = ev / lines;                                               // 总增益 x256
    if (g < 256u) g = 256u;
    // 模拟增益 65536/(256-code) 取不超过 g 的最大档
    code = (g >= AG_X256_MAX) ? IMX219_AG_MAX : 256u - (65536u + g - 1u) / g;
    a  = 65536u / (256u - code);
    dg = g * 256u / a;
    if (dg < 0x100u) dg = 0x100u;
    if (dg > DG_MAX) dg = DG_MAX;
    if (lines != cur_lines) { imx219_set_exposure(lines); cur_lines = lines; }
    if (code != cur_code)   { imx219_set_again(code);     cur_code = code; }
    if (dg != cur_dg)       { imx219_set_dgain(dg);       cur_dg = dg; }
}

static uint32_t clampu(uint32_t v, uint32_t lo, uint32_t hi) { return v < lo ? lo : v > hi ? hi : v; }

// 返回 1 表示曝光有变化
static int ae_step(const cam_stat_t *s, uint32_t y16)
{
    uint32_t r, m;
    if (y16 < 16u) y16 = 16u;                                     // 均值 < 1 按 1 算
    r = clampu(Y_TARGET * 16u * 256u / y16, 32u, 2048u);          // 目标/当前，8.8
    if (r >= 243u && r <= 269u) m = 256u;                         // ±5% 死区
    else m = clampu(((r * r >> 8) + 256u) >> 1, 128u, 512u);
    if (s->nhi > NPIX / 25u && m > 256u) m = 256u;
    if (s->nhi > NPIX / 12u && m > 243u) m = 243u;
    if (s->nhi > NPIX / 2u) m = 64u;                              // 大面积饱和：均值低估过曝程度，直接降到 1/4
    if (m == 256u) return 0;
    uint32_t e = (uint32_t)(((uint64_t)ev * m) >> 8);
    e = clampu(e, EV_MIN, EV_MAX);
    if (e == ev) return 0;
    ev = e;
    apply_ev();
    return 1;
}

// 通道增益 g 使该通道和 sc 向 G 通道和 sg 对齐
static uint32_t wb_adj(uint32_t g, uint32_t sg, uint32_t sc)
{
    uint32_t q, m;
    if (sc < NPIX) sc = NPIX;
    q = clampu((uint32_t)(((uint64_t)sg << 8) / sc), 128u, 512u);
    if (q >= 250u && q <= 262u) return g;                         // ±2.3% 死区
    m = clampu(((q * q >> 8) + 3u * 256u) >> 2, 230u, 282u);
    return clampu(g * m >> 8, WB_MIN, WB_MAX);
}

void isp_init(int skip)
{
    skip_rows = skip;
    vision_cam_ctrl(BLK, 1, skip_rows);
    vision_cam_bayer(orient);
    vision_cam_gains(gr, GG, gb);
    apply_ev();
    cam_stat_t s;
    vision_cam_stat(&s);
    last_seq = s.seq;
    hold = 2;
}

int isp_poll(void)
{
    cam_stat_t s;
    vision_cam_stat(&s);
    if (s.seq == last_seq) return 0;
    last_seq = s.seq;
    uint32_t y16 = (s.sr + 2u * s.sg + s.sb) / (NPIX * 4u / 16u);  // 平均亮度 x16
    y16_last = y16;
    if (!auto_on || tp_on) return 1;
    if (hold) { hold--; return 1; }
    if (ae_step(&s, y16)) hold = 2;
    if (y16 >= 30u * 16u && y16 <= 200u * 16u) {
        uint32_t nr = wb_adj(gr, s.sg, s.sr), nb = wb_adj(gb, s.sg, s.sb);
        if (nr != gr || nb != gb) { gr = nr; gb = nb; vision_cam_gains(gr, GG, gb); }
    }
    return 1;
}

void isp_auto(int on) { auto_on = on; hold = 2; }
int  isp_auto_on(void) { return auto_on; }

void isp_manual_ev(int dir)
{
    auto_on = 0;
    ev = clampu(dir > 0 ? ev / 8u * 9u : ev / 8u * 7u, EV_MIN, EV_MAX);
    apply_ev();
}

int isp_flip(void)
{
    orient = (orient + 1) & 3;
    vision_cam_bayer(imx219_set_orient(orient));
    hold = 2;
    return orient;
}

void isp_test_pattern(int on)
{
    tp_on = on;
    imx219_test_pattern(on ? 2 : 0);
    if (on) {
        vision_cam_ctrl(0, 0, skip_rows);
        vision_cam_gains(256, 256, 256);
    } else {
        vision_cam_ctrl(BLK, 1, skip_rows);
        vision_cam_gains(gr, GG, gb);
        hold = 2;
    }
}

int isp_skip_toggle(void)
{
    skip_rows = skip_rows ? 0 : 2;
    if (tp_on) vision_cam_ctrl(0, 0, skip_rows);
    else       vision_cam_ctrl(BLK, 1, skip_rows);
    return skip_rows;
}

static char *put_u(char *p, uint32_t v)
{
    char t[12];
    int n = 0;
    do { t[n++] = (char)('0' + v % 10u); v /= 10u; } while (v);
    while (n) *p++ = t[--n];
    return p;
}

static char *put_s(char *p, const char *s)
{
    while (*s) *p++ = *s++;
    return p;
}

void isp_status(char *buf)
{
    char *p = buf;
    p = put_s(p, "Y ");    p = put_u(p, y16_last >> 4);
    p = put_s(p, " EXP "); p = put_u(p, cur_lines);
    p = put_s(p, " AG ");  p = put_u(p, cur_code);
    p = put_s(p, " DG ");  p = put_u(p, cur_dg);
    p = put_s(p, " WB ");  p = put_u(p, gr); *p++ = '/'; p = put_u(p, GG); *p++ = '/'; p = put_u(p, gb);
    p = put_s(p, auto_on ? " AUTO" : " MANUAL");
    if (tp_on) p = put_s(p, " TP");
    if (skip_rows) p = put_s(p, " SKIP2");
    *p = 0;
}
