"""Application wiring: QApplication + orchestrator + hook + tray + overlay + main window."""
import logging
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from .config import Config
from .hotkey import CapsLockHook
from .orchestrator import Orchestrator
from .ui import theme
from .ui.main_window import MainWindow
from .ui.overlay import Overlay
from .ui.tray import Tray

log = logging.getLogger(__name__)


class FlowLocalApp:
    def __init__(self, argv: list[str]):
        self.qt = QApplication(argv)
        self.qt.setQuitOnLastWindowClosed(False)
        self.qt.setApplicationName("FlowLocal")
        self.qt.setStyleSheet(theme.QSS)

        self.cfg = Config.load()
        self.orch = Orchestrator(self.cfg)
        self.overlay = Overlay()
        self.window = MainWindow(self.cfg, self.orch)
        self.tray = Tray(
            on_pause=self._toggle_pause,
            on_settings=lambda: self.window.open_page(MainWindow.PAGE_SETTINGS),
            on_history=lambda: self.window.open_page(MainWindow.PAGE_HISTORY),
            on_quit=self.quit,
        )
        self.tray.activated.connect(self._tray_activated)

        # app icon (window title bar, taskbar) — also used by the desktop shortcut
        from .startup import app_icon_path, write_app_icon

        icon_file = app_icon_path()
        if not icon_file.exists():
            write_app_icon(icon_file)
        self.qt.setWindowIcon(QIcon(str(icon_file)))

        # orchestrator signals arrive queued on the Qt main thread
        self.orch.state_changed.connect(self.overlay.set_state)
        self.orch.state_changed.connect(self.tray.set_state)
        self.orch.state_changed.connect(self.window.set_state)
        self.orch.state_changed.connect(lambda s, d: log.info("state: %s %s", s, d))

        self.hook = CapsLockHook(
            on_press=self.orch.on_press,
            on_release=self.orch.on_release,
            on_tap=self.orch.on_tap,
            tap_threshold_s=self.cfg.tap_threshold_s,
        )

    def run(self) -> int:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            QMessageBox.critical(None, "FlowLocal", "System tray is not available.")
            return 1
        self.tray.show()
        if self.cfg.cleanup_enabled and not self.orch.cleaner.health_check():
            msg = (
                "Ollama is not running — dictations will paste raw text.\n"
                "Start Ollama (or install from ollama.com) for AI cleanup."
                if self.cfg.cleanup_backend == "ollama"
                else "Cleanup API is unreachable — dictations will paste raw text.\n"
                "Check the API settings in Settings → Models & AI."
            )
            self.tray.showMessage("FlowLocal", msg, QSystemTrayIcon.Warning, 8000)
        self.orch.start()
        try:
            self.hook.start()
        except OSError as e:
            QMessageBox.critical(None, "FlowLocal", f"Keyboard hook failed: {e}")
            return 1
        rc = self.qt.exec()
        self.hook.stop()  # CapsLock behaves normally again after quit
        self.orch.shutdown()
        return rc

    # -- tray actions --------------------------------------------------------
    def _tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.window.open_page(MainWindow.PAGE_OVERVIEW)

    def _toggle_pause(self) -> None:
        paused = self.orch.toggle_pause()
        # while paused, CapsLock passes through and works as a normal key
        self.hook.enabled = not paused

    def quit(self) -> None:
        self.qt.quit()


def main() -> int:
    from .startup import acquire_single_instance, create_desktop_shortcut, set_autostart

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    if not acquire_single_instance():
        print("FlowLocal is already running (check the system tray).")
        return 0
    app = FlowLocalApp(sys.argv)
    try:
        create_desktop_shortcut()  # idempotent: keeps the Desktop icon fresh
        if app.cfg.autostart:
            set_autostart(True)
    except Exception as e:
        log.warning("Shortcut creation failed: %s", e)
    return app.run()
