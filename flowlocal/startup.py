"""Run-at-startup and single-instance guards."""
import ctypes
import sys
from pathlib import Path

APP_MUTEX = "FlowLocal_SingleInstance_Mutex"
ERROR_ALREADY_EXISTS = 183

STARTUP_DIR = Path.home() / "AppData/Roaming/Microsoft/Windows/Start Menu/Programs/Startup"
SHORTCUT = STARTUP_DIR / "FlowLocal.lnk"


def acquire_single_instance() -> bool:
    """True if we are the only instance. The mutex lives until process exit."""
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW(None, False, APP_MUTEX)
    return kernel32.GetLastError() != ERROR_ALREADY_EXISTS


def set_autostart(enabled: bool) -> None:
    if not enabled:
        SHORTCUT.unlink(missing_ok=True)
        return
    import win32com.client

    pythonw = Path(sys.executable).parent / "pythonw.exe"
    target_script = Path(__file__).resolve().parents[1] / "run_flowlocal.pyw"
    shell = win32com.client.Dispatch("WScript.Shell")
    lnk = shell.CreateShortcut(str(SHORTCUT))
    lnk.TargetPath = str(pythonw)
    lnk.Arguments = f'"{target_script}"'
    lnk.WorkingDirectory = str(target_script.parent)
    lnk.Description = "FlowLocal voice-to-text"
    lnk.Save()
