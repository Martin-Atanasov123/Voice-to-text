"""Application wiring: QApplication + orchestrator + hook + tray + overlay + main window."""
import logging
import logging.handlers
import sys

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from .config import Config
from .hotkey import PTTHook
from .keymap import MODIFIER_VK
from .orchestrator import Orchestrator
from .ui import theme
from . import inserter
from .ui.clipboard_popup import ClipboardPopup, ResultViewer
from .ui.main_window import MainWindow
from .ui.overlay import Overlay
from .ui.rewrite_popup import RewritePopup
from .ui.tray import Tray

log = logging.getLogger(__name__)


def _setup_logging() -> None:
    """Console + rotating file — pythonw has no console, so failures must land
    in %APPDATA%\\FlowLocal\\flowlocal.log to be diagnosable at all."""
    from .config import APP_DIR

    APP_DIR.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    try:
        handlers.append(
            logging.handlers.RotatingFileHandler(
                APP_DIR / "flowlocal.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8"
            )
        )
    except OSError:
        pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        handlers=handlers,
    )


class _ShowBridge(QObject):
    """Marshals 'show the window' requests from the watcher thread to Qt."""

    show_requested = Signal()


class _OllamaBridge(QObject):
    """Marshals the 'still unreachable after auto-start' notice from the
    recovery thread to Qt (tray.showMessage must run on the Qt thread)."""

    still_down = Signal(str)


class FlowLocalApp:
    def __init__(self, argv: list[str]):
        self.qt = QApplication(argv)
        self.qt.setQuitOnLastWindowClosed(False)
        self.qt.setApplicationName("FlowLocal")
        self.qt.setStyleSheet(theme.QSS)

        self.cfg = Config.load()
        self.orch = Orchestrator(self.cfg)
        self.overlay = Overlay()

        # hook is built before the window: the Hotkeys settings page needs a
        # live reference to capture new keys (see begin_capture in hotkey.py)
        self.hook = PTTHook(
            on_press=self.orch.on_press,
            on_release=self.orch.on_release,
            on_tap=self.orch.on_tap,
            tap_threshold_s=self.cfg.tap_threshold_s,
            on_combo=self.orch.on_combo,
            primary_vk=self.cfg.ptt_vk,
            primary_extended=self.cfg.ptt_extended,
            rewrite_modifier_vk=MODIFIER_VK.get(self.cfg.rewrite_modifier, MODIFIER_VK["ctrl"]),
            command_modifier_vk=MODIFIER_VK.get(self.cfg.command_modifier, MODIFIER_VK["shift"]),
        )

        self.window = MainWindow(
            self.cfg, self.orch, capture_key_fn=self.hook.begin_capture, hook=self.hook
        )
        self.tray = Tray(
            on_pause=self._toggle_pause,
            on_settings=lambda: self.window.open_page(MainWindow.PAGE_SETTINGS),
            on_history=lambda: self.window.open_page(MainWindow.PAGE_HISTORY),
            on_quit=self.quit,
        )
        self.tray.activated.connect(self._tray_activated)

        self.rewrite_popup = RewritePopup()
        self.orch.rewrite_ready.connect(self.rewrite_popup.show_at_cursor)
        self.rewrite_popup.style_chosen.connect(self.orch.choose_rewrite_style)
        self.rewrite_popup.dismissed.connect(self.orch.cancel_rewrite)

        # clipboard AI: react to copies the USER makes, never to our own ops
        self.clip_popup = ClipboardPopup()
        self.result_viewer = ResultViewer()
        self._last_clip = ""
        self.clip_popup.action_chosen.connect(self.orch.run_clipboard_action)
        self.orch.clipboard_result.connect(self.result_viewer.present)
        if self.cfg.clipboard_ai_enabled:
            self.qt.clipboard().dataChanged.connect(self._clipboard_changed)

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

    def run(self) -> int:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            QMessageBox.critical(None, "FlowLocal", "System tray is not available.")
            return 1
        self.tray.show()
        # the window opens on launch and on every re-launch of the desktop icon
        from .startup import watch_show_requests

        self._show_bridge = _ShowBridge()
        self._show_bridge.show_requested.connect(
            lambda: self.window.open_page(MainWindow.PAGE_OVERVIEW)
        )
        watch_show_requests(self._show_bridge.show_requested.emit)
        self.window.open_page(MainWindow.PAGE_OVERVIEW)
        if self.cfg.cleanup_enabled and not self.orch.cleaner.health_check():
            if self.cfg.cleanup_backend == "ollama":
                self._ollama_bridge = _OllamaBridge()
                self._ollama_bridge.still_down.connect(
                    lambda msg: self.tray.showMessage("FlowLocal", msg, QSystemTrayIcon.Warning, 8000)
                )
                self._try_recover_ollama()
            else:
                msg = (
                    "Cleanup API is unreachable — dictations will paste raw text.\n"
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

    def _try_recover_ollama(self) -> None:
        """Ollama has to be manually launched after each reboot (its own
        Startup entry only fires at login, and it doesn't stay running once
        closed) — so the 'not running' toast was showing up on most launches.
        Try to start it ourselves first and only nag if that doesn't work."""
        import threading
        import time

        from .cleanup import try_start_ollama

        def work() -> None:
            if not try_start_ollama():
                self._ollama_bridge.still_down.emit(
                    "Ollama is not running — dictations will paste raw text.\n"
                    "Start Ollama (or install from ollama.com) for AI cleanup."
                )
                return
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                if self.orch.cleaner.health_check():
                    log.info("Ollama came up automatically")
                    return
                time.sleep(1)
            self._ollama_bridge.still_down.emit(
                "Ollama didn't finish starting — dictations will paste raw text.\n"
                "Open it manually if this keeps happening."
            )

        threading.Thread(target=work, daemon=True).start()

    # -- clipboard AI ----------------------------------------------------------
    def _clipboard_changed(self) -> None:
        import time

        from PySide6.QtGui import QGuiApplication

        from .clipboard_ai import MAX_CHARS, MIN_CHARS

        if time.monotonic() < inserter.suppress_until:
            return  # our own paste/capture/restore
        if QGuiApplication.focusWindow() is not None:
            return  # copy made inside FlowLocal's own windows
        if self.orch.state != "IDLE":
            return
        text = self.qt.clipboard().text()
        if not text or not (MIN_CHARS <= len(text) <= MAX_CHARS):
            return
        if text == self._last_clip:
            return  # same content copied again — don't nag
        self._last_clip = text
        self.clip_popup.offer(text)

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
    from .startup import (
        acquire_single_instance,
        create_desktop_shortcut,
        set_autostart,
        signal_running_instance,
    )

    _setup_logging()
    if not acquire_single_instance():
        # second double-click of the icon = "show me the window"
        signal_running_instance()
        log.info("FlowLocal already running — asked it to show its window.")
        return 0
    try:
        app = FlowLocalApp(sys.argv)
    except Exception:
        log.exception("FlowLocal failed to start")
        fallback = QApplication.instance() or QApplication(sys.argv)
        QMessageBox.critical(
            None, "FlowLocal",
            "FlowLocal failed to start.\nDetails are in %APPDATA%\\FlowLocal\\flowlocal.log",
        )
        return 1
    try:
        create_desktop_shortcut()  # idempotent: keeps the Desktop icon fresh
        if app.cfg.autostart:
            set_autostart(True)
    except Exception as e:
        log.warning("Shortcut creation failed: %s", e)
    return app.run()
