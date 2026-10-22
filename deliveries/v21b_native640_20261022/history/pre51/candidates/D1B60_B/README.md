> 分类：研究附件 / 不可启动。原firmware CRC拒D1，不能烧录此组合。

> LATEST49：旧D1B60_B位流616e40bb…配D1blob会被原固件CRC拒绝，启动BLOCKED。独立CRC修复候选见candidates/D1B60_B_CRC，BIT3f302996…/HEX8fc0a9be…，本地交叉编译+RV32加载器+ROM更新验证，尚未完整启动/板测/采纳；20:00监督选择未定。原RISCV11回退保留。详见evidence/DP3_BLOB_LOAD.md。

# D1B60 B-level candidate — NOT ADOPTED; UNTESTED ON BOARD

Native640×480 topology; original shared kernels/UK/ink parameters; VG270 gamma/beta words changed. The BIT and blob are a matched pair: old ROM would autonomously overwrite new startup affine coefficients. Do not describe blob-only replacement as persistent deployment.

This directory stages reviewable artifacts, not a20:00 selection. No board programming, screen test or power-cycle test was done. OriginalRISCV11 rollback is ../../rollback_RISCV11. All BIT/HEX/firmware/blob SHA and ROM assets are in MANIFEST.json; SOURCE.json binds434 formal-source inputs and the six changed mem files.

B gate: local full interface/map/PnR passed at56824XLR/243RAM10/145DSP,+.240ns setup/+.026ns hold, identical resource totals to local original. Tool2026.1.132; historical original tool.132.4.5 yielded55615XLR(+2.1739%local difference). Sole causal attribution to version is unproved. See FULL_BUILD.md. Historical original29.99–30.01fps is quoted reference evidence only; this new bitstream's FPS/10min OSD/power-cycle behavior are unverified. <100ms switch lacks raw sampling evidence.

Art: VG object hue increment acceptedCC47/48; complete curved brushwork/paint masses unmet. HG1 native640 expanded16val+30camera raw/warp .803714/.795645. DP2 complete autonomousIN engine passed0LSB on three styles total9frames32×24,6912pixels/936coefficients, not native640 timing.20:00 supervision decides whether B may be the delivery network; all new bitstreams must retain untested-on-board labeling.
