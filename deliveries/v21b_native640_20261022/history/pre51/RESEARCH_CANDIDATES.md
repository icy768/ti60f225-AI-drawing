> LATEST50：原固件常量补丁FWP1验证完成，首选候选candidates/D1B60_B_FWP1，BITd05ca9a28994…，仍待20:00监督选择；未完整启动/板测/采纳。GCC15修复仅备选（整份重编译风险）；旧B616e40bb…+D1明确CRC_BLOCKED/研究附件不可启动。原RISCV11回退保留。见evidence/FW_PATCH_RESULT.md与FINAL_DECISION.md。

> LATEST49：旧D1B60_B位流616e40bb…配D1blob会被原固件CRC拒绝，启动BLOCKED。独立CRC修复候选见candidates/D1B60_B_CRC，BIT3f302996…/HEX8fc0a9be…，本地交叉编译+RV32加载器+ROM更新验证，尚未完整启动/板测/采纳；20:00监督选择未定。原RISCV11回退保留。详见evidence/DP3_BLOB_LOAD.md。

# 当前研究候选状态（LATEST47，2026-10-22 14:04）

D1B60已获监督艺术增量与视频PASS；局限为VG色相改善，纹理变柔，弯曲笔块未达。基线ROM逐字节复现PASS、D1只VG gamma/beta变化。原版整机编译资源/时序未精确复现，按停止条件不出新候选bitstream、不采纳。DP2自主IN仿真已完成：32×24三风格9帧、6912像素/936系数0LSB，结果不能解除DP1阻断，也不是VGA时序或板测。

J1_60的UK/ink回归及J3_INK/J3_UK_R1三风格盲页均齐备，等待独立监督；J3两个分支已1000QAT、导出评估正常完成，数值抽检0LSB不代表艺术通过。研究权重与可选blob均不进入冻结baseline。原BIT/HEX/固件/blob已保存rollback_RISCV11供回退，无新板测。

以下为历史部署问题的源码依据；其中旧“待扩大审图/请求确认”不代表当前状态。

---
# 研究候选
D1B60经LATEST45初判胜出，16val+camera30整数视频数值门通过，但扩大艺术审图待确认。

# 可选blob部署阻断：自主IN常量ROM
核验时间 2026-10-22T12:28:55.344145+08:00。硬件源sc_engine.v参数IN_FILE=model/in_constants.mem，实例sc_in_refresh(CONSTFILE=IN_FILE)。sc_in_refresh.v通过initial readmemh读取.p0..p9和.ec0..ec1常量ROM，gamma/beta从packed_p解包，并驱动sc_in_math重新计算每帧M/B；接口没有写gamma/beta ROM的cfg口。现有blob只配置卷积权重与启动M/B bank。
因此只改VG启动M/B的blob，在原bitstream持续自主刷新时，会被原gamma/beta重新计算覆盖。CPU当前帧新affine的18/扩展图与固定新M/B的旧13层conv_layer RTL通过，不能证明最新sc_engine在原bitstream长期保持新affine。不能声称新blob是持久可用的零bitstream替换。
原bitstream只改启动VG系数的diff/范围/CRC仍作为有限研究产物，不能作为部署可选文件晋级；当前HG0的CPU-RTL算术证据与整机运行合同分开。需要监督明确路线：参数ROM运行时可写的小RTL/新bitstream验证，或既有正式RTL中确有受支持参数加载路径的实证。不能拿暂停自主IN刷新替代，现APB未见开关，不能固件常数模式。
本轮不改原硬件、不烧录，交付网络仍冻结原v21b。请求下一监督核实并纠正118/119/14:00的可选blob假设。源文件路径D:/fpga/tristyle_v4_20261017/reports/paired_v7/HW/IN_COLOR_PROBE_01/hardware_source/sc_engine.v与sc_in_refresh.v；需对照最新正式提交确认无新增接口。

目前不在冻结baseline内放入新blob；R44/D1B60/HG0/optional_blob仅算术研究产物，未经采纳/未经板测。