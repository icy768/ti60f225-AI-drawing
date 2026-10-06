"""Find Icarus Verilog tools on PATH or in IVERILOG_BIN."""
import os
import shutil
from pathlib import Path


def executable(name):
    directory = os.environ.get("IVERILOG_BIN")
    if directory:
        path = Path(directory) / name
        if path.is_file():
            return str(path)
    bundled = Path(__file__).resolve().parent.parent / "tools/iverilog/mingw64/bin" / name
    if bundled.is_file():
        return str(bundled)
    found = shutil.which(name)
    if found:
        return found
    raise FileNotFoundError(f"{name} not found; add Icarus Verilog to PATH or set IVERILOG_BIN")
