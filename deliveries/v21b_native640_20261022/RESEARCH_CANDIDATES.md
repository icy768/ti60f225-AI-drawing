# 部署与研究附件边界

选定交付：candidates/D1B60_B_FWP1；名称中candidates是原目录名，角色已于LATEST51 17:15改为交付网络，未经板测。原RISCV11为回退。

GCC15整份重编译修复candidates/D1B60_B_CRC不部署；原B candidates/D1B60_B的616e40bb…配D1被CRC拒绝，不可启动。J1–J6盲页在research/R44；D1之外的J线没有获胜/不部署。720p原样NO_GO，窄GI/RTL研究估算无训练/完整验证。

原bitstream每帧从gamma/beta ROM刷新IN会覆盖blob启动M/B，所以D1使用匹配新VGROM位流和blob。首选FWP1再仅更新CPU CRC常量ROM，未改INROM/显示ROM/路由。不能只换blob或混用两套CRC。
