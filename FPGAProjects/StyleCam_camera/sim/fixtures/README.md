# VGA reference fixture

`vga_reference.zip` contains the exact input, official golden output, weights/IN records and provenance from the passing full 640×480 reference test. Entry SHA256 values are checked before use; the decoded output image hash is checked separately. The fixture keeps `sim_latency_vga.py` runnable in a fresh checkout without the local training dataset or ignored simulation folders.

Run `python -X utf8 sim_latency_vga.py --check-vectors` for data checks only. A full RTL run additionally needs Icarus Verilog at `FPGAProjects/tools/iverilog/mingw64/bin`. The generated executables and logs stay in ignored validation folders. Rebuilding golden vectors from the source image uses `sim_vga_performance.py`, the training dependencies and the local validation dataset.
