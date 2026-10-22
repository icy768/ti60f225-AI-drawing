# DP3 B: B_PASS_UNTESTED_ON_BOARD

Completed full interface/map/PnR of D1B60 using formal RISCV11 sources, isolated in DP3/D1B60. Only six model/in_constants.mem* source files changed; all434 source SHA checked after build, RTL/constraints/project/firmware unchanged from the completed local original. D1 blob remains a separate48616B load file.

| Measure | Local original | D1B60 |
|---|---:|---:|
|XLR|56824|56824|
|RAM10|243|243|
|DSP|145|145|
|Minimum setup slack ns|+.240|+0.240|
|Minimum hold slack ns|+.026|+0.026|

XLR difference relative to local original: 0.000000%; limit1%. All17 setup and17 hold clock relationships checked. Resource/source/timing B gate: PASS. See RESULT.json for report/BIT/HEX SHA and SOURCE.json for full input provenance.

Historical original used55615XLR/243RAM10/145DSP,+.253/+.026 with reported tool2026.1.132.4.5. Local tool2026.1.132 original differs by+2.1739%XLR; observed version difference has not been proven the sole cause. This is a different bitstream, not a historical exact reproduction and not a historical-layout BRAM patch. A was unavailable locally; no A identity test was run.

**No new board test, no programming, no automatic adoption.** Software/RTL correctness and PnR do not measure FPS or screen behavior. Historical29.99–30.01fps is reference evidence for the original, not measurement of this bitstream.20:00 supervision chooses the delivery network. OriginalBIT/HEX/firmware/blob rollback remains protected.
