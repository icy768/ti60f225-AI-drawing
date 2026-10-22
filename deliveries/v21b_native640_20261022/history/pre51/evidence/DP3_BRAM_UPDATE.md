# DP3 A: unavailable, not passed

Formal RISCV11 commit 47254c25a6e767d7602da96a4529fb84616c9524 contains BIT/HEX and reports, but no placement, LBF or RAM-information protocol-buffer files. A full local D:/fpga file inventory (including ignored files) found vendor/demo, old isolated-core, and new local DP1 layouts; none is bound to the historical BIT SHA 0b7c2d11f0ee3ae176721b208d0d4934191479b80d708f803787c0234835e3f4. Sibling BIT SHA checks and complete paths are in A_SEARCH.json. The September vendor example is not RISCV11. No alternate drive or hardware-team machine was inspected.

D:/bin/efx_bram_edit.exe --help confirms --project, --mem_info, --place, --lbf, --memory and update/read/revert. The required historical inputs are absent locally. Therefore no historical-layout identity update was attempted, and no A-level candidate is permitted. A patch on the newly compiled layout would not satisfy the required identity gate. Proceed to B under LATEST48, comparing against the already completed local original 56824/243/145. No board programming.

Archive index follow-up: inspected 10 relevant local StyleCam/tristyle/hardware-handoff ZIP central directories read-only; matches and errors in ARCHIVE_SEARCH.json. No archive was modified. No layout entries found.
