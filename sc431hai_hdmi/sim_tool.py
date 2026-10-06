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
    found = shutil.which(name)
    if found:
        return found
    raise FileNotFoundError(f"{name} not found; add Icarus Verilog to PATH or set IVERILOG_BIN")
