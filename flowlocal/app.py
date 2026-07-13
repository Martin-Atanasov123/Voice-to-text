"""Application wiring: QApplication + orchestrator + hook + tray + overlay."""
import logging
import sys

from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from .config import Config
from .hotkey import CapsLockHook
from .orchestrator import Orchestrator
from .ui.history_window import HistoryWindow
from .ui.overlay import Overlay
from .ui.settings_window import SettingsWindow
from .ui.tray import Tray

log = logging.getLogger(__name__)


class FlowLocalApp:
    def __init__(self, argv: list[str]):
        self.qt = QApplication(argv)
        self.qt.setQuitOnLastWindowClosed(False)
        self.qt.setApplicationName("FlowLocal")

        self.cfg = Config.load()
        self.orch = Orchestrator(self.cfg)
        self.overlay = Overlay()
        self.tray = Tray(
            on_pause=self._toggle_pause,
            on_settings=self._show_settings,
            on_history=self._show_history,
            on_quit=self.quit,
        )
        self._settings_win: SettingsWindow | None = None
        self._history_win: HistoryWindow | None = None

        # orchestrator signals arrive queued on the Qt main thread
        self.orch.state_changed.connect(self.overlay.set_state)
        self.orch.state_changed.connect(self.tray.set_state)
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
                "Check the API settings in the Models dashboard."
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
    def _toggle_pause(self) -> None:
        paused = self.orch.toggle_pause()
        # while paused, CapsLock passes through and works as a normal key
        self.hook.enabled = not paused

    def _show_settings(self) -> None:
        if self._settings_win is None:
            self._settings_win = SettingsWindow(self.cfg)
        self._settings_win.show()
        self._settings_win.raise_()
        self._settings_win.activateWindow()

    def _show_history(self) -> None:
        if self._history_win is None:
            self._history_win = HistoryWindow(self.orch.history)
        self._history_win.refresh()
        self._history_win.show()
        self._history_win.raise_()
        self._history_win.activateWindow()

    def quit(self) -> None:
        self.qt.quit()


def main() -> int:
    from .startup import acquire_single_instance, set_autostart

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    if not acquire_single_instance():
        print("FlowLocal is already running (check the system tray).")
        return 0
    app = FlowLocalApp(sys.argv)
    if app.cfg.autostart:
        try:
            set_autostart(True)  # idempotent: refreshes the startup shortcut
        except Exception as e:
            log.warning("Could not create startup shortcut: %s", e)
    return app.run()
