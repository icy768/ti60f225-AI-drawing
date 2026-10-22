> LATEST48 scope update: the exact historical reproduction result below is retained. Its round47 blanket stop has been superseded by the graded DP3 gate; D1B60 B passed relative to the local original. See [DP3 full build](../DP3/FULL_BUILD.md). No new board test or adoption.

# DP1 baseline reproduction failed; new bitstream delivery blocked

Local formal47254c full interface/map/PnR finished13:42 with original RTL/mem/constraints. No board programming.

| measure | historical formal | current local |
|---|---:|---:|
|tool|2026.1.132.4.5|2026.1.132|
|XLR|55615|56824|
|RAM10|243|243|
|DSP|145|145|
|minimum setup ns|+.253|+0.240|
|minimum hold ns|+.026|+0.026|

XLR delta +1209 (+2.1739%). Timing is positive, but exact baseline resources/timing were not reproduced. UnderLATEST47 item125c and its explicit stopping condition, **no new candidate bitstream may be delivered**, and no candidate bitstream compile is started. Network research/DP2 evidence can continue as attachments. Existing original formal BIT/HEX/firmware/blob are copied by Git bytes to DELIVERY_20261022/rollback_RISCV11; BIT SHA matches historical0b7c2d11... .

The executables FileVersion/ProductVersion are2026.1.132; historical reports specify2026.1.132.4.5. Original build.py default path D:/ELS/efinity/2026.1 is absent. All433 archived files other than XML stayed byte-identical. Efinity rewrote XML whitespace/root sw_version to2026.1.132; no design/constraint/synthesis/PnR option changed. Source manifest in SOURCE.json. Version difference is observed, not proof it alone caused resource delta. No unsupported source/timing/resource change is used to force a pass.

Raw place/timing/hier reports remain baseline/outflow; SHA in BUILD_REPRODUCTION.json. Two launcher option errors before actual successfulPnR are retained in BUILD_QUEUE.json/logs, separate from this measured mismatch.
