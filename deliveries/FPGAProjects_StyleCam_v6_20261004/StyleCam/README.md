# StyleCam v6 hardware handoff

Start with [the delivery guide](../交付说明.md).

This is a verified integer-network and vision-subsystem source handoff, not a completed board bitstream. The vendor camera images contain no neural style network. `sw/board_profile.h` intentionally requires confirmation of the actual board memory map and clocks before vision startup.

The current synthesis entry is `syn/vision_map.xml`; the matched model is `rtl/gen/v6_cal100_640x480`. Source, headers, coefficient banks, quantization constants, and generated RTL must stay together.

See `docs/PC验证报告.md`, `docs/板级集成与烧录步骤.md`, and `docs/硬件组实测与回填.md` for verified scope and the required board measurements.
