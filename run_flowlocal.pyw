"""Windowless launcher for the startup shortcut (target with pythonw.exe)."""
import runpy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
runpy.run_module("flowlocal", run_name="__main__")
