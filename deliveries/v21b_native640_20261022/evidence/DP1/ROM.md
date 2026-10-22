> LATEST48 scope update: the exact historical reproduction result below is retained. Its round47 blanket stop has been superseded by the graded DP3 gate; D1B60 B passed relative to the local original. See [DP3 full build](../DP3/FULL_BUILD.md). No new board test or adoption.

## Latest result

[Original full build failed reproduction](BUILD_REPRODUCTION.md):56824/243/145,+.240/+.026; localtool2026.1.132 versus historical.132.4.5. New candidate bitstream delivery blocked under47. Baseline mem byte identity remainsPASS.

# DP1 ROM / deployment evidence

LATEST47, 2026-10-22. Formal source commit47254c25a6e767d7602da96a4529fb84616c9524, extracted bytes/SHA in SOURCE.json. The baseline project remains unchanged; candidate assets are separate.

Baseline checkpoint was freshly exported to baseline_from_checkpoint.{npz,json}; both match F0/baseline_reexport and formal calibrated qparams byte-for-byte. Original export_in_constants.py and compact_in_constants.py regenerate ALL existing in_constants.mem files byte-for-byte (full304bit words, parameters/epsilon, p0..p9, legacy e0..e2, ec0..ec1). See ROM_RESULT.json. There are864 address slots,816 active channels=272 per style,12 IN layers. Not816 total address slots.

D1B60 changes270 full-ROM words, all inside VG style0 address slots. Only gamma/beta bits differ; all epsilon bits and all UK/ink words remain exact. Ten512x20 parameter banks and two512x20 epsilon banks are lossless serial layouts; padding is kept. Full304bit ROM is a source/debug representation, not another simultaneously instantiated large ROM.

sc_in_refresh.v g_compact explicitly infers twelve block_ram memories. Historical formal hierarchical PnR report in_update has12 RAM10 (source reports/paired_v7/hardware_repo_audit_20261018/hier_util.rpt). This is BRAM initialization, not LUT constants. Fresh synthesis/PnR allocation remains to be compared when the baseline build finishes.

Efinity installed documentation D:/doc/topics/efn-bram-updater.html explicitly supports replacing BRAM initial content without full compilation; CLI docs efx-bram-updater-cli.html take elaborated logical-memory name+init file, memory-info protocol buffer, placement and LBF. Installed executable is D:/bin/efx_bram_edit.exe (help inspected); docs call it efx_bram_update. Updated LBF requires regenerated bitstream. This is not a live runtime ROM write and is not a firmware-only fix. Documentation warns intermediate map.v is not updated, and optimize-zero-init-rom may remove zero ROMs (formal option is1).

The tool capability is documented, but this project's exact logical-name mapping/readback/update has NOT yet been validated. Do not claim a patched candidate bitstream exists. Under LATEST47, baseline resource/timing reproduction and candidate full compile remain mandatory; do not substitute an unchecked BRAM patch for these gates. Original BIT/HEX/blob are rollback assets. No board programming/testing is scheduled before delivery.

Baseline interface succeeded; map/PnR running in BUILD_QUEUE.json. Target55615XLR/243RAM10/145DSP, setup+.253ns/hold+.026ns. No successful reproduction claim yet. If baseline mem or build cannot reproduce, new bitstream delivery is barred.
