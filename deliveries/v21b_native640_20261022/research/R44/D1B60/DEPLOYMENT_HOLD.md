# LATEST48 supersedes47: DP3 B_PASS, selection pending

Historical exact build reproduction failed. A unavailable locally, B full build passed, see DP3/RESULT.json;20:00 supervision decision pending. No adoption before resource/timing/source gates and supervision decision. See ../../DP3/BRAM_UPDATE.md and ../../DP3/FULL_BUILD.md. Single blob cannot persist new affine without the new ROM.

---
# LATEST47: DP1 reproduction FAILED; new bitstream delivery blocked

Original full interface/map/PnR succeeded, but56824XLR/+0.240ns setup did not reproduce historical55615/+0.253ns. See ../../DP1/BUILD_REPRODUCTION.md. No candidate new-bitstream compile/delivery. Baseline ROM byte reproduction passed; DP2 remains separate functional evidence. Documented BRAM init update is not project-validated and does not bypass this gate. Original v21b rollback stays delivery baseline.

---
# 可选blob部署阻断：自主IN常量ROM
核验时间 2026-10-22T12:28:55.344145+08:00。硬件源sc_engine.v参数IN_FILE=model/in_constants.mem，实例sc_in_refresh(CONSTFILE=IN_FILE)。sc_in_refresh.v通过initial readmemh读取.p0..p9和.ec0..ec1常量ROM，gamma/beta从packed_p解包，并驱动sc_in_math重新计算每帧M/B；接口没有写gamma/beta ROM的cfg口。现有blob只配置卷积权重与启动M/B bank。
因此只改VG启动M/B的blob，在原bitstream持续自主刷新时，会被原gamma/beta重新计算覆盖。CPU当前帧新affine的18/扩展图与固定新M/B的旧13层conv_layer RTL通过，不能证明最新sc_engine在原bitstream长期保持新affine。不能声称新blob是持久可用的零bitstream替换。
原bitstream只改启动VG系数的diff/范围/CRC仍作为有限研究产物，不能作为部署可选文件晋级；当前HG0的CPU-RTL算术证据与整机运行合同分开。需要监督明确路线：参数ROM运行时可写的小RTL/新bitstream验证，或既有正式RTL中确有受支持参数加载路径的实证。不能拿暂停自主IN刷新替代，现APB未见开关，不能固件常数模式。
本轮不改原硬件、不烧录，交付网络仍冻结原v21b。请求下一监督核实并纠正118/119/14:00的可选blob假设。源文件路径D:/fpga/tristyle_v4_20261017/reports/paired_v7/HW/IN_COLOR_PROBE_01/hardware_source/sc_engine.v与sc_in_refresh.v；需对照最新正式提交确认无新增接口。
