// PC 端固件测试：模拟视觉子系统寄存器，驱动 vision.c 的 IN 逐帧刷新逻辑
// 输入 stats.txt（每行：层号 通道 Σa Σa²），输出 cfg/style 写记录，由 algo/test_fw.py 比对
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include "vision.h"
#include "in_params.h"

static int64_t  S1[32][64];
static uint64_t S2[32][64];
static int stat_layer, stat_idx;
static uint32_t cfg_addr, cfg_lo;
static FILE *fo;

void host_wr(uint32_t off, uint32_t v)
{
    switch (off) {
    case V_STAT_CTRL: stat_layer = (int)(v & 31); fprintf(fo, "arm %u\n", v & 31); break;
    case V_STAT_IDX:  stat_idx = (int)v; break;
    case V_CFG_ADDR:  cfg_addr = v; break;
    case V_CFG_DLO:   cfg_lo = v; break;
    case V_CFG_DHI:   fprintf(fo, "cfg %u %u %u\n", cfg_addr, cfg_lo, v); break;
    case V_STYLE:     fprintf(fo, "style %u\n", v); break;
    default: break;
    }
}

uint32_t host_rd(uint32_t off)
{
    switch (off) {
    case V_ID:         return 0x53544C31u;
    case V_STAT_CTRL:  return 1u;                                   // 统计已完成
    case V_STAT_S1_LO: return (uint32_t)S1[stat_layer][stat_idx];
    case V_STAT_S1_HI: return (uint32_t)((uint64_t)S1[stat_layer][stat_idx] >> 32);
    case V_STAT_S2_LO: return (uint32_t)S2[stat_layer][stat_idx];
    case V_STAT_S2_HI: return (uint32_t)(S2[stat_layer][stat_idx] >> 32);
    default:           return 0;
    }
}

int main(int argc, char **argv)
{
    if (argc < 4) { fprintf(stderr, "用法: host_test stats.txt out.txt style\n"); return 1; }
    FILE *fi = fopen(argv[1], "r");
    fo = fopen(argv[2], "w");
    int style = atoi(argv[3]), l, c;
    long long a;
    unsigned long long b;
    while (fscanf(fi, "%d %d %lld %llu", &l, &c, &a, &b) == 4) { S1[l][c] = a; S2[l][c] = b; }
    fclose(fi);
    vision_set_style(style);
    in_refresh_enable(1);
    for (int i = 0; i < 2 * IN_NLAYER + 1; i++) in_refresh_poll();
    fclose(fo);
    return 0;
}
