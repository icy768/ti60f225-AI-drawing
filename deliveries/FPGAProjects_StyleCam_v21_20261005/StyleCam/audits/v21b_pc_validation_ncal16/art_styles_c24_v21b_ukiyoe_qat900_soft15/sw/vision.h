// 风格化视觉子系统驱动（寄存器定义与接口），对应 rtl/vision_core.v
#ifndef VISION_H
#define VISION_H
#include <stdint.h>

// 寄存器偏移（字节）
#define V_ID          0x000   // 只读 0x53544C31 "STL1"
#define V_CTRL        0x004   // [0] NN 使能 [1] 软复位(自清) [3:2] 显示模式
#define V_STYLE       0x008   // [3:0] 系数槽号（风格 s 占槽 2s、2s+1）
#define V_STATUS      0x00C   // [0] NN 忙 [1] 摄像头写忙
#define V_CAM_FRAMES  0x010
#define V_NN_FRAMES   0x014
#define V_NN_CYCLES   0x018   // 最近一帧 NN 处理周期数（AXI 时钟）
#define V_DISP_FRAMES 0x01C
#define V_CFG_ADDR    0x020   // [31] 0 系数/1 权重 [25:21] 32 位分道 [20:16] 层号 [11:0] 地址
#define V_CFG_DLO     0x024
#define V_CFG_DHI     0x028   // 写即提交一次 cfg 写
#define V_BUF_BASE    0x02C
#define V_IRQ_STATUS  0x030   // [0] NN 帧完成 [1] 摄像头帧完成，写 1 清
#define V_IRQ_EN      0x034
#define V_TIMER       0x038   // AXI 时钟自由计数
#define V_UNDERFLOW   0x03C   // 显示欠载计数
#define V_STAT_CTRL   0x040   // 写：[4:0] 层号并预备；读：[1] busy [0] done
#define V_STAT_IDX    0x044
#define V_STAT_S1_LO  0x048
#define V_STAT_S1_HI  0x04C   // 符号扩展
#define V_STAT_S2_LO  0x050
#define V_STAT_S2_HI  0x054
#define V_MOT_TH      0x058   // 运动块判定阈值（8x8 块平均亮度差）
#define V_MOT_CNT     0x05C   // 上一帧运动块数
#define V_MOT_SX      0x060   // 运动块 x 坐标和（块单位，每行 NW/8 块）
#define V_MOT_SY      0x064
#define V_MOT_FRAMES  0x068   // 运动检测完成帧数
#define V_CAM_BAYER   0x06C   // [1:0] 左上像素颜色 0=R(RGGB) 1=Gr 2=Gb 3=B
#define V_CAM_GR      0x070   // 白平衡增益 R/G/B，8.8 定点（256 = 1 倍）
#define V_CAM_GG      0x074
#define V_CAM_GB      0x078
#define V_CAM_CTRL    0x07C   // [9:0] 黑电平 [12] gamma [17:16] 帧首跳过行数 [24] 模组使能
#define V_CAM_SR      0x080   // 上一摄像头帧（640x480，8 位 sRGB）R/G/B 之和
#define V_CAM_SG      0x084
#define V_CAM_SB      0x088
#define V_CAM_NHI     0x08C   // 任一通道 >= 250 的像素数
#define V_CAM_SSEQ    0x090   // 统计帧序号
#define V_OSD         0x800   // 文字 RAM：每字 4 字符，低字节在前

#define DISP_SIDE     0       // 左原图右风格图
#define DISP_FULL_STY 1       // 风格图 1.5 倍全屏
#define DISP_FULL_ORG 2       // 原图 1.5 倍全屏

#define OSD_COLS      80
#define OSD_ROWS      22
#define OSD_YELLOW    0x80    // 字符码 bit7：黄色

uint32_t vision_id(void);
int      vision_load_blob(const uint32_t *blob, uint32_t nwords);
void     vision_enable(int en);
void     vision_set_mode(int mode);
void     vision_set_style(int style);          // 风格号 0..NET_NSTYLE-1
int      vision_style(void);
uint32_t vision_timer(void);
uint32_t vision_nn_frames(void);
uint32_t vision_nn_cycles(void);
uint32_t vision_cam_frames(void);
uint32_t vision_underflow(void);

// 摄像头前端（raw_bin2）与帧统计
typedef struct { uint32_t sr, sg, sb, nhi, seq; } cam_stat_t;
void vision_cam_power(int on);                               // 模组使能脚（IMX219 XCLR）
void vision_cam_ctrl(uint32_t blk, int gamma, int skip);     // 黑电平、gamma、帧首跳过行数
void vision_cam_bayer(int bayer);
void vision_cam_gains(uint32_t gr, uint32_t gg, uint32_t gb);
void vision_cam_stat(cam_stat_t *s);                         // 读一致的一组统计值

// 挥手手势：返回 +1 右挥、-1 左挥、0 无（每帧调用一次即可，内部按运动帧号去重）
void vision_set_motion_th(int th);
int  gesture_poll(void);

void osd_clear(void);
void osd_puts(int row, int col, const char *s, int yellow);

// IN 逐帧刷新（分时统计）：每次调用检查统计是否完成，完成则刷新一层并轮换
void in_refresh_enable(int en);
int  in_refresh_poll(void);                    // 返回本次是否刷新了一层
int  in_refresh_enabled(void);

#endif
