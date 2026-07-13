"""Make the nvidia pip-wheel CUDA DLLs loadable by ctranslate2.

MUST run before the first `faster_whisper` / `ctranslate2` import.

Three mechanisms, because ctranslate2 resolves DLLs inconsistently:
- os.add_dll_directory: covers import-time dependent DLLs
- PATH prepend: covers plain LoadLibrary calls at inference time
- ctypes.WinDLL preload: pins cublas/cudnn into the process outright
  (without this, encode() fails with "Library cublas64_12.dll is not found")
"""
import ctypes
import os
import site
import sys
from pathlib import Path


def setup_cuda_dlls() -> None:
    candidates = list(site.getsitepackages())
    # venvs sometimes omit their own site-packages from getsitepackages()
    candidates.append(str(Path(sys.prefix) / "Lib" / "site-packages"))
    dll_dirs = []
    for sp in candidates:
        for sub in ("nvidia/cublas/bin", "nvidia/cudnn/bin"):
            p = Path(sp) / sub
            if p.is_dir() and p not in dll_dirs:
                dll_dirs.append(p)

    for d in dll_dirs:
        os.add_dll_directory(str(d))
        os.environ["PATH"] = str(d) + os.pathsep + os.environ.get("PATH", "")

    for d in dll_dirs:
        for dll in d.glob("*.dll"):
            try:
                ctypes.WinDLL(str(dll))
            except OSError:
                pass  # optional DLLs may have unmet deps; core ones will load
