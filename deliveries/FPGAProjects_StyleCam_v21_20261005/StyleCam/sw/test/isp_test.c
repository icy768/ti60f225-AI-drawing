// PC 端 AE/AWB 闭环测试：isp.c + 传感器/场景/FPGA 前端模型
//   场景：640x480 像素反射率纹理（含 2% 高光）× 光源各通道响应 × 亮度 Lv
//   传感器：RAW10 = 64 + 反射率 x 响应 x Lv x 曝光行数 x 模拟增益 x 数字增益 + 噪声，饱和 1023；
//           曝光/增益寄存器在第 k 帧统计后写入，第 k+2 帧生效（卷帘曝光时序）
//   FPGA 前端：与 raw_bin2 相同的整数运算（扣黑电平、8.8 白平衡、sRGB 表），统计与 vision_core 相同
//   判据：收敛后 Y 在目标 ±8% 内、R/G 与 B/G 均值比在 ±5% 内（增益未触限时）、最后 30 帧曝光量变化 ≤2 次、
//         起始或阶跃后 45 帧（1.5s）内 Y 进入 ±10% 且此后不再离开
#include <math.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include "vision.h"
#include "imx219.h"
#include "isp.h"

#define NP (640 * 480)

// ---------------- 桩：HAL / 传感器 / 视觉子系统 ----------------
void hal_delay_ms(uint32_t ms) { (void)ms; }
void hal_puts(const char *s) { fputs(s, stdout); }

static uint32_t w_exp = 1000, w_ag, w_dg = 0x100;       // 最近写入的寄存器
static uint32_t a_exp = 1000, a_ag, a_dg = 0x100;       // 当前帧生效值
static uint32_t p_exp[4], p_ag[4], p_dg[4];             // 生效流水
void imx219_set_exposure(uint32_t l) { w_exp = l; }
void imx219_set_again(uint32_t c)    { w_ag = c; }
void imx219_set_dgain(uint32_t g)    { w_dg = g; }
int  imx219_set_orient(int hv)       { return hv & 3; }
void imx219_test_pattern(int m)      { (void)m; }

static uint32_t f_gr = 256, f_gg = 256, f_gb = 256, f_blk = 64, f_gam = 1;
static cam_stat_t st;
void vision_cam_power(int on) { (void)on; }
void vision_cam_ctrl(uint32_t blk, int gamma, int skip) { f_blk = blk; f_gam = (uint32_t)gamma; (void)skip; }
void vision_cam_bayer(int b) { (void)b; }
void vision_cam_gains(uint32_t gr, uint32_t gg, uint32_t gb) { f_gr = gr; f_gg = gg; f_gb = gb; }
void vision_cam_stat(cam_stat_t *s) { *s = st; }

// ---------------- 模型 ----------------
static uint8_t gam[1024];
static float refl[NP];

static uint32_t hash(uint32_t x)
{
    x ^= x >> 16; x *= 0x7feb352dU; x ^= x >> 15; x *= 0x846ca68bU; x ^= x >> 16;
    return x;
}

static void init_model(void)
{
    for (int i = 0; i < 1024; i++) {
        double x = i / 1023.0;
        double y = x <= 0.0031308 ? 12.92 * x : 1.055 * pow(x, 1 / 2.4) - 0.055;
        int v = (int)(y * 255 + 0.5);
        gam[i] = (uint8_t)(v > 255 ? 255 : v);
    }
    for (int i = 0; i < NP; i++) {
        float u = (hash((uint32_t)i) & 0xFFFF) / 65535.0f;
        refl[i] = (hash((uint32_t)i * 7u + 3u) % 50 == 0) ? 3.0f : 0.03f + 0.8f * u * u;
    }
}

static uint32_t wb(uint32_t v, uint32_t g)
{
    uint32_t t = v * g + 256u;
    return (t >> 9) > 1023u ? 1023u : t >> 9;
}

// 渲染一帧并生成统计；lv：场景亮度，resp：光源 x 传感器各通道响应
static void frame(float lv, const float resp[3], uint32_t seq)
{
    float gain = 256.0f / (256.0f - (float)a_ag) * (float)a_dg / 256.0f;
    uint32_t sum[3] = {0, 0, 0}, nhi = 0;
    for (int i = 0; i < NP; i++) {
        uint32_t o[3];
        for (int c = 0; c < 3; c++) {
            int noise = (int)(hash((uint32_t)i * 3u + (uint32_t)c + seq * 1000003u) % 5) - 2;
            float sig = refl[i] * resp[c] * lv * (float)a_exp * gain;
            int raw = 64 + (int)(sig > 2000.0f ? 2000.0f : sig) + noise;
            if (raw > 1023) raw = 1023;
            if (raw < 0) raw = 0;
            // raw_bin2：G 为两个 G 之和（此处两个 G 取同值），R/B 为 2 倍
            uint32_t v2 = c == 1 ? (uint32_t)(2 * raw > (int)(2 * f_blk) ? 2 * raw - (int)(2 * f_blk) : 0)
                                 : (uint32_t)(raw > (int)f_blk ? 2 * (raw - (int)f_blk) : 0);
            uint32_t g = c == 0 ? f_gr : c == 1 ? f_gg : f_gb;
            uint32_t v10 = wb(v2, g);
            o[c] = f_gam ? gam[v10] : v10 >> 2;
            sum[c] += o[c];
        }
        if (o[0] >= 250 || o[1] >= 250 || o[2] >= 250) nhi++;
    }
    st.sr = sum[0]; st.sg = sum[1]; st.sb = sum[2]; st.nhi = nhi; st.seq = seq;
}

static int run(const char *name, int nf, float lv0, float lv1, int step_at, const float resp[3])
{
    uint32_t hist_ev[512];
    float y = 0, rg = 0, bg = 0;
    int ok = 1, t0 = step_at < nf ? step_at : 0, conv = -1;
    for (int k = 0; k < 4; k++) { p_exp[k] = w_exp; p_ag[k] = w_ag; p_dg[k] = w_dg; }
    for (int k = 0; k < nf; k++) {
        // 生效流水：第 k 帧使用第 k-2 帧统计后写入的值
        a_exp = p_exp[(k + 2) % 4]; a_ag = p_ag[(k + 2) % 4]; a_dg = p_dg[(k + 2) % 4];
        frame(k < step_at ? lv0 : lv1, resp, (uint32_t)(k + 1));
        isp_poll();
        p_exp[k % 4] = w_exp; p_ag[k % 4] = w_ag; p_dg[k % 4] = w_dg;
        hist_ev[k] = w_exp * 100000u + w_ag * 1000u + w_dg;
        y  = (st.sr + 2.0f * st.sg + st.sb) / 4.0f / NP;
        rg = (float)st.sr / (float)st.sg;
        bg = (float)st.sb / (float)st.sg;
        if (k >= t0) {
            int in = fabsf(y - 115.0f) <= 11.5f;
            if (in && conv < 0) conv = k - t0;
            if (!in) conv = -1;
        }
    }
    int changes = 0;
    for (int k = nf - 30; k < nf; k++) changes += hist_ev[k] != hist_ev[k - 1];
    char s[128];
    isp_status(s);
    int wb_lim = f_gr <= 200 || f_gr >= 1200 || f_gb <= 200 || f_gb >= 1200;
    if (fabsf(y - 115.0f) > 115.0f * 0.08f) ok = 0;
    if (!wb_lim && (fabsf(rg - 1) > 0.05f || fabsf(bg - 1) > 0.05f)) ok = 0;
    if (changes > 2) ok = 0;
    if (conv < 0 || conv > 45) ok = 0;
    printf("%-22s Y=%6.1f R/G=%.3f B/G=%.3f 收敛 %d 帧 末30帧曝光变化 %d  [%s]  %s\n",
           name, y, rg, bg, conv, changes, s, ok ? "PASS" : "FAIL");
    return ok;
}

int main(void)
{
    init_model();
    isp_init(0);
    const float neutral[3] = {0.55f, 1.0f, 0.65f};     // 日光下 IMX219 典型：G 最强
    const float warm[3]    = {0.95f, 1.0f, 0.35f};     // 白炽灯
    const float cool[3]    = {0.40f, 1.0f, 0.90f};     // 阴天/冷白 LED
    int ok = 1;
    ok &= run("室内（中等亮度）", 150, 0.6f, 0.6f, 999, neutral);
    ok &= run("暗光（需增益）", 200, 0.03f, 0.03f, 999, neutral);
    ok &= run("室外强光", 150, 40.0f, 40.0f, 999, neutral);
    ok &= run("开灯阶跃 x20", 200, 0.05f, 1.0f, 100, neutral);
    ok &= run("关灯阶跃 /20", 200, 1.0f, 0.05f, 100, neutral);
    ok &= run("白炽灯偏色", 200, 0.6f, 0.6f, 999, warm);
    ok &= run("冷光偏色", 200, 0.6f, 0.6f, 999, cool);
    printf("AE/AWB %s\n", ok ? "PASS" : "FAIL");
    return ok ? 0 : 1;
}
