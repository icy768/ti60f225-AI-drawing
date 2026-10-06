// 风格化视觉子系统驱动实现
#include <math.h>
#include "hal.h"
#include "vision.h"
#include "net_blob.h"
#include "in_params.h"

#ifndef VISION_HOST_TEST
#define REG_WR(off, v) (*(volatile uint32_t *)(VISION_BASE + (off)) = (uint32_t)(v))
#define REG_RD(off)    (*(volatile uint32_t *)(VISION_BASE + (off)))
#else   // PC 端测试：寄存器访问转为函数调用（见 sw/test/host_test.c）
void host_wr(uint32_t off, uint32_t v);
uint32_t host_rd(uint32_t off);
#define REG_WR(off, v) host_wr((off), (uint32_t)(v))
#define REG_RD(off)    host_rd(off)
#endif

static int cur_style, cur_bank;
static uint8_t osd_shadow[OSD_COLS * OSD_ROWS];

uint32_t vision_id(void)         { return REG_RD(V_ID); }
uint32_t vision_timer(void)      { return REG_RD(V_TIMER); }
uint32_t vision_nn_frames(void)  { return REG_RD(V_NN_FRAMES); }
uint32_t vision_nn_cycles(void)  { return REG_RD(V_NN_CYCLES); }
uint32_t vision_cam_frames(void) { return REG_RD(V_CAM_FRAMES); }
uint32_t vision_underflow(void)  { return REG_RD(V_UNDERFLOW); }
int      vision_style(void)      { return cur_style; }

static uint32_t ctrl_shadow;

void vision_enable(int en)
{
    ctrl_shadow = (ctrl_shadow & ~1u) | (en ? 1u : 0u);
    REG_WR(V_CTRL, ctrl_shadow);
}

void vision_set_mode(int mode)
{
    ctrl_shadow = (ctrl_shadow & ~0xCu) | ((uint32_t)(mode & 3) << 2);
    REG_WR(V_CTRL, ctrl_shadow);
}

static void cfg_write(uint32_t addr, uint32_t lo, uint32_t hi)
{
    REG_WR(V_CFG_ADDR, addr);
    REG_WR(V_CFG_DLO, lo);
    REG_WR(V_CFG_DHI, hi);
}

// 装载权重与各风格系数镜像（格式见 algo/export_blob.py）
int vision_load_blob(const uint32_t *blob, uint32_t nwords)
{
    if (!blob || nwords < 4 || blob[0] != 0x53544E31u) return -1;
    uint32_t n = blob[1];
    if (n == 0 || n > (nwords - 4u) / 3u || 4u + 3u * n != nwords) return -2;
    if (blob[2] != NET_NSTYLE || blob[3] != 0) return -3;
    const uint32_t *p = blob + 4;
    for (uint32_t i = 0; i < n; i++, p += 3) cfg_write(p[0], p[1], p[2]);
    return (int)n;
}

int vision_set_buffer_base(uint32_t base)
{
    if ((base & 0x1fffffu) || base > UINT32_MAX - STYLECAM_FRAME_RESERVED_BYTES) return -1;
    REG_WR(V_BUF_BASE, base);
    return REG_RD(V_BUF_BASE) == base ? 0 : -2;
}

// ---------------- IN 逐帧刷新 ----------------
// 流程：预备统计层 L → 该层统计完成 → 计算新 M/Bq → 写入非活动槽（连同上一层的更新）
//       → 切换活动槽（下一 NN 帧起生效）→ 预备下一层。写非活动槽不会影响正在处理的帧。
static int in_en, in_idx = -1, prev_valid;
static int prev_layer_i;
static int32_t prev_M[32], prev_B[32];

static void in_compute(const in_layer_t *L, int style, int32_t *M, int32_t *B)
{
    double n = (double)L->npix, pr = ldexp(1.0, L->R);
    for (int c = 0; c < L->cout; c++) {
        REG_WR(V_STAT_IDX, (uint32_t)c);
        // 统计值在 M10K 里、位于 NN 时钟域：通道号改后要过跨时钟 + 1 拍读出，先空读两次留出余量
        (void)REG_RD(V_STAT_IDX);
        (void)REG_RD(V_STAT_IDX);
        // S1_HI 已按 40 位符号扩展到 32 位，拼成 64 位补码即为有符号值
        uint64_t u1 = ((uint64_t)REG_RD(V_STAT_S1_HI) << 32) | REG_RD(V_STAT_S1_LO);
        int64_t s1 = (int64_t)u1;
        uint64_t s2 = ((uint64_t)REG_RD(V_STAT_S2_HI) << 32) | REG_RD(V_STAT_S2_LO);
        double mean = (double)s1 / n;
        double var = (double)s2 / n - mean * mean;
        if (var < 0) var = 0;
        double k = L->k[c];
        double mu_v = mean * pr * k;
        double sig = sqrt(var * pr * pr * k * k + L->eps);
        double g = L->gamma[style * L->cout + c], b = L->beta[style * L->cout + c];
        double mult = g * k / sig, add = b - g * mu_v / sig;
        long long m = llround(mult / L->s_y * ldexp(1.0, L->S + L->R));
        long long q = llround(add / L->s_y * (double)(1 << IN_S2)) + (1 << (IN_S2 - 1));
        if (m > 131071) m = 131071;
        if (m < -131072) m = -131072;
        if (q > 524287) q = 524287;
        if (q < -524288) q = -524288;
        M[c] = (int32_t)m;
        B[c] = (int32_t)q;
    }
}

static void coef_write(int layer, int cout, int bank, const int32_t *M, const int32_t *B)
{
    for (int c = 0; c < cout; c++) {
        uint32_t m = (uint32_t)M[c] & 0x3FFFFu, q = (uint32_t)B[c] & 0xFFFFFu;
        cfg_write(((uint32_t)layer << 16) | (uint32_t)(bank * cout + c), (m << 20) | q, m >> 12);
    }
}

void in_refresh_enable(int en)
{
    in_en = en;
    in_idx = -1;
    prev_valid = 0;
}

int in_refresh_enabled(void) { return in_en; }

int in_refresh_poll(void)
{
    if (!in_en) return 0;
    if (in_idx < 0) {                       // 启动：预备第 0 个 IN 层
        in_idx = 0;
        REG_WR(V_STAT_CTRL, (uint32_t)in_layers[0].layer);
        return 0;
    }
    if (!(REG_RD(V_STAT_CTRL) & 1u)) return 0; // 统计未完成
    const in_layer_t *L = &in_layers[in_idx];
    int32_t M[32], B[32];
    in_compute(L, cur_style, M, B);
    int other = (cur_bank == 2 * cur_style) ? cur_bank + 1 : cur_bank - 1;
    coef_write(L->layer, L->cout, other, M, B);
    if (prev_valid)                         // 同步上一轮写入另一槽的更新
        coef_write(in_layers[prev_layer_i].layer, in_layers[prev_layer_i].cout, other, prev_M, prev_B);
    cur_bank = other;
    REG_WR(V_STYLE, (uint32_t)cur_bank);      // 下一 NN 帧起生效
    for (int c = 0; c < L->cout; c++) { prev_M[c] = M[c]; prev_B[c] = B[c]; }
    prev_layer_i = in_idx;
    prev_valid = 1;
    in_idx = (in_idx + 1) % IN_NLAYER;
    REG_WR(V_STAT_CTRL, (uint32_t)in_layers[in_idx].layer);   // 预备下一层（统计从下一帧开始）
    return 1;
}

void vision_set_style(int style)
{
    if (style < 0 || style >= NET_NSTYLE) return;
    cur_style = style;
    cur_bank = 2 * style;
    REG_WR(V_STYLE, (uint32_t)cur_bank);       // 两槽均为镜像中的初始系数，切换在下一 NN 帧生效
    if (in_en) in_refresh_enable(1);          // 新风格重新开始轮换
}

// ---------------- 挥手手势 ----------------
// 运动质心 x（百分比）在约 0.7 秒内由 <35% 移到 >65% 判为右挥，反之左挥；触发后冷却 1 秒
#define MOT_BW      40      // 640/16（运动检测 16x16 分块）
#define MOT_MIN     4       // 有效运动的最少块数（过滤噪声）
#define MOT_MAX     400     // 过多说明是整体光照/镜头晃动（共 1200 块）
#define GEST_WIN    20      // 窗口帧数
#define GEST_COOL   30

static uint32_t mot_last;
static int gx[GEST_WIN], gn, gcool;

// ---------------- 摄像头前端 ----------------
static uint32_t cam_ctrl_shadow = 64u | (1u << 12);         // 复位值：黑电平 64、gamma 开、模组关

void vision_cam_power(int on)
{
    cam_ctrl_shadow = (cam_ctrl_shadow & ~(1u << 24)) | (on ? 1u << 24 : 0u);
    REG_WR(V_CAM_CTRL, cam_ctrl_shadow);
}

void vision_cam_ctrl(uint32_t blk, int gamma, int skip)
{
    cam_ctrl_shadow = (cam_ctrl_shadow & (1u << 24)) | (blk & 0x3FFu) | (gamma ? 1u << 12 : 0u) |
                      ((uint32_t)(skip & 3) << 16);
    REG_WR(V_CAM_CTRL, cam_ctrl_shadow);
}

void vision_cam_bayer(int bayer) { REG_WR(V_CAM_BAYER, (uint32_t)(bayer & 3)); }

void vision_cam_gains(uint32_t gr, uint32_t gg, uint32_t gb)
{
    REG_WR(V_CAM_GR, gr);
    REG_WR(V_CAM_GG, gg);
    REG_WR(V_CAM_GB, gb);
}

void vision_cam_stat(cam_stat_t *s)
{
    uint32_t q;
    do {    // 读取期间若统计更新（帧写完），重读
        q      = REG_RD(V_CAM_SSEQ);
        s->sr  = REG_RD(V_CAM_SR);
        s->sg  = REG_RD(V_CAM_SG);
        s->sb  = REG_RD(V_CAM_SB);
        s->nhi = REG_RD(V_CAM_NHI);
        s->seq = REG_RD(V_CAM_SSEQ);
    } while (s->seq != q);
}

void vision_set_motion_th(int th) { REG_WR(V_MOT_TH, (uint32_t)th); }

int gesture_poll(void)
{
    uint32_t f = REG_RD(V_MOT_FRAMES);
    if (f == mot_last) return 0;
    mot_last = f;
    if (gcool > 0) { gcool--; gn = 0; return 0; }
    uint32_t cnt = REG_RD(V_MOT_CNT);
    if (cnt < MOT_MIN || cnt > MOT_MAX) {
        if (gn > 0) gn--;                   // 短暂静止容忍，逐步淡出
        return 0;
    }
    int cx = (int)(REG_RD(V_MOT_SX) * 100u / (cnt * MOT_BW));
    if (gn == GEST_WIN) {
        for (int i = 1; i < GEST_WIN; i++) gx[i - 1] = gx[i];
        gn--;
    }
    gx[gn++] = cx;
    if (gn < 4) return 0;
    int first = gx[0], last = gx[gn - 1], dir = 0;
    if (first < 35 && last > 65) dir = 1;
    else if (first > 65 && last < 35) dir = -1;
    if (dir) { gn = 0; gcool = GEST_COOL; }
    return dir;
}

// ---------------- OSD ----------------
static void osd_flush_word(int idx)
{
    int w = idx & ~3;
    REG_WR(V_OSD + (uint32_t)w, (uint32_t)osd_shadow[w] | (uint32_t)osd_shadow[w + 1] << 8 |
                               (uint32_t)osd_shadow[w + 2] << 16 | (uint32_t)osd_shadow[w + 3] << 24);
}

void osd_clear(void)
{
    for (int i = 0; i < OSD_COLS * OSD_ROWS; i++) osd_shadow[i] = 0;
    for (int i = 0; i < OSD_COLS * OSD_ROWS; i += 4) osd_flush_word(i);
}

void osd_puts(int row, int col, const char *s, int yellow)
{
    int idx = row * OSD_COLS + col, last = -1;
    for (; *s && col < OSD_COLS; s++, col++, idx++) {
        osd_shadow[idx] = (uint8_t)((*s & 0x7F) | (yellow ? OSD_YELLOW : 0));
        if ((idx & ~3) != last) {
            if (last >= 0) osd_flush_word(last);
            last = idx & ~3;
        }
    }
    if (last >= 0) osd_flush_word(last);
}
