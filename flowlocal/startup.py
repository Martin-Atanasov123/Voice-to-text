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


def _make_shortcut(path: Path, icon: Path | None = None) -> None:
    import win32com.client

    pythonw = Path(sys.executable).parent / "pythonw.exe"
    target_script = Path(__file__).resolve().parents[1] / "run_flowlocal.pyw"
    shell = win32com.client.Dispatch("WScript.Shell")
    lnk = shell.CreateShortcut(str(path))
    lnk.TargetPath = str(pythonw)
    lnk.Arguments = f'"{target_script}"'
    lnk.WorkingDirectory = str(target_script.parent)
    lnk.Description = "FlowLocal voice-to-text"
    if icon is not None and icon.exists():
        lnk.IconLocation = str(icon)
    lnk.Save()


def set_autostart(enabled: bool) -> None:
    if not enabled:
        SHORTCUT.unlink(missing_ok=True)
        return
    _make_shortcut(SHORTCUT)


def app_icon_path() -> Path:
    """Render the app icon to %APPDATA%\\FlowLocal\\flowlocal.ico once (Qt must be up)."""
    from .config import APP_DIR

    return APP_DIR / "flowlocal.ico"


def write_app_icon(path: Path) -> None:
    """Paint the amber-mic-on-dark icon and save as .ico. Requires a QApplication."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QBrush, QColor, QPainter, QPixmap

    pm = QPixmap(256, 256)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(QColor("#1E1A14")))
    p.drawRoundedRect(8, 8, 240, 240, 56, 56)
    p.setBrush(QBrush(QColor("#F5A623")))
    p.drawRoundedRect(103, 56, 50, 92, 25, 25)   # mic capsule
    p.drawRect(120, 160, 16, 28)                  # stem
    p.drawRoundedRect(88, 190, 80, 14, 7, 7)      # base
    p.end()
    path.parent.mkdir(parents=True, exist_ok=True)
    pm.save(str(path), "ICO")


def create_desktop_shortcut() -> None:
    """Idempotent: (re)creates the FlowLocal icon on the user's Desktop."""
    icon = app_icon_path()
    if not icon.exists():
        write_app_icon(icon)
    desktop = Path.home() / "Desktop"
    if not desktop.exists():  # OneDrive-redirected desktops
        desktop = Path.home() / "OneDrive" / "Desktop"
    if desktop.exists():
        _make_shortcut(desktop / "FlowLocal.lnk", icon)
