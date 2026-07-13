"""Pipeline orchestrator: state machine + worker thread.

States: LOADING -> IDLE <-> RECORDING -> TRANSCRIBING -> CLEANING -> PASTING -> IDLE
plus PAUSED and transient BUSY/WARNING/ERROR notifications to the UI.

Threading:
- hook thread calls on_press/on_release/on_tap: state check + enqueue only
- one worker thread runs the whole pipeline (single in-flight dictation)
- UI updates leave this class ONLY as Qt signals (queued to the main thread)
"""
import ctypes
import ctypes.wintypes
import logging
import queue
import threading
import time

from PySide6.QtCore import QObject, Signal

from .audio import Recorder
from .cleanup import OllamaCleaner
from .config import Config
from .history import History
from .inserter import insert_text
from .layout import get_dictation_language
from .stt import Transcriber

log = logging.getLogger(__name__)

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


def _foreground_exe() -> str:
    """Process name of the focused window, for history records."""
    try:
        import psutil  # optional; not in requirements — graceful degrade
    except ImportError:
        psutil = None
    try:
        hwnd = user32.GetForegroundWindow()
        pid = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if psutil:
            return psutil.Process(pid.value).name()
        return str(pid.value)
    except Exception:
        return "?"


class Orchestrator(QObject):
    # state name + human detail; UI (overlay/tray) renders from this alone
    state_changed = Signal(str, str)

    def __init__(self, cfg: Config):
        super().__init__()
        self.cfg = cfg
        self.state = "LOADING"
        self._state_lock = threading.Lock()
        self.recorder = Recorder(cfg.mic_device, cfg.max_record_s)
        self.stt = Transcriber(cfg.whisper_model, cfg.whisper_device, cfg.whisper_model_hq, cfg.beam_size)
        self.cleaner = OllamaCleaner(
            cfg.ollama_url,
            {"en": cfg.ollama_model_en, "bg": cfg.ollama_model_bg},
            cfg.cleanup_timeout_s,
        )
        self.history = History()
        self.ollama_ok = False
        self._cmds: queue.Queue = queue.Queue()
        self._worker = threading.Thread(target=self._run, name="pipeline", daemon=True)
        self._ctx: dict = {}

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        self._worker.start()
        threading.Thread(target=self._preload, name="preload", daemon=True).start()

    def _preload(self) -> None:
        self._set_state("LOADING", "loading speech model…")
        try:
            self.stt.load()
        except Exception as e:
            self._set_state("ERROR", f"speech model failed: {e}")
            return
        self.ollama_ok = self.cleaner.health_check()
        if self.cfg.cleanup_enabled and self.ollama_ok:
            self._set_state("LOADING", "warming up cleanup model…")
            self.cleaner.warm_up()
        detail = f"whisper {self.stt.active[0]}/{self.stt.active[1]}"
        if self.cfg.cleanup_enabled and not self.ollama_ok:
            detail += " — Ollama not running, will paste raw text"
        self._set_state("IDLE", detail)

    def shutdown(self) -> None:
        self._cmds.put(("quit", None))
        self._worker.join(timeout=3.0)
        self.history.close()

    # -- state helpers -----------------------------------------------------
    def _set_state(self, state: str, detail: str = "") -> None:
        with self._state_lock:
            self.state = state
        self.state_changed.emit(state, detail)

    def _flash(self, kind: str, detail: str) -> None:
        """Transient overlay notification that does not change the real state."""
        self.state_changed.emit(kind, detail)

    # -- hook-thread entry points (must return in microseconds) -------------
    def on_press(self) -> None:
        with self._state_lock:
            if self.state == "PAUSED":
                return
            if self.state != "IDLE":
                busy = self.state
            else:
                busy = None
        if busy == "LOADING":
            self._flash("BUSY", "still loading — try again in a moment")
            return
        if busy:
            self._flash("BUSY", "busy with previous dictation")
            return
        self._cmds.put(("start", None))

    def on_release(self, held: float) -> None:
        self._cmds.put(("finish", held))

    def on_tap(self) -> None:
        self._cmds.put(("cancel", None))

    def toggle_pause(self) -> bool:
        """Returns True when now paused."""
        with self._state_lock:
            if self.state == "PAUSED":
                self.state = "IDLE"
                paused = False
            elif self.state == "IDLE":
                self.state = "PAUSED"
                paused = True
            else:
                return False
        self.state_changed.emit(self.state, "")
        return paused

    # -- worker ------------------------------------------------------------
    def _run(self) -> None:
        while True:
            cmd, arg = self._cmds.get()
            try:
                if cmd == "quit":
                    return
                elif cmd == "start":
                    self._do_start()
                elif cmd == "cancel":
                    self._do_cancel()
                elif cmd == "finish":
                    self._do_finish(arg)
            except Exception as e:
                log.exception("pipeline error")
                self._set_state("ERROR", str(e))
                time.sleep(1.5)
                self._set_state("IDLE", "")
            finally:
                self._cmds.task_done()

    def _do_start(self) -> None:
        self._ctx = {
            "language": get_dictation_language(),
            "app": _foreground_exe(),
            "t0": time.monotonic(),
        }
        self.recorder.start()
        self._set_state("RECORDING", self._ctx["language"])

    def _do_cancel(self) -> None:
        if self.state == "RECORDING":
            self.recorder.stop()
            self._set_state("IDLE", "")

    def _do_finish(self, held: float | None) -> None:
        if self.state != "RECORDING":
            return
        audio = self.recorder.stop()
        lang = self._ctx.get("language", "en")
        t0 = self._ctx.get("t0", time.monotonic())
        if audio.size < 1600:  # <0.1s of audio
            self._set_state("IDLE", "")
            return

        self._set_state("TRANSCRIBING", f"{audio.size / 16000:.0f}s of speech")
        raw = self.stt.transcribe(audio, lang)
        if not raw:
            self._flash("WARNING", "didn't catch that")
            self._set_state("IDLE", "")
            return

        text, status = raw, "cleanup_off"
        if self.cfg.cleanup_enabled:
            self._set_state("CLEANING", "")
            cleaned, ok = self.cleaner.clean(raw, lang)
            if ok:
                text, status = cleaned, "cleaned"
            else:
                status = "raw_fallback"
                self._flash("WARNING", "cleanup failed — pasting raw text")

        self._set_state("PASTING", "")
        try:
            insert_text(text)
        except Exception as e:
            log.warning("paste failed: %s", e)
            self._flash("ERROR", "paste failed — text is in history")
            status = "error"

        self.history.add(
            language=lang,
            raw_text=raw,
            cleaned_text=text if status == "cleaned" else None,
            target_app=self._ctx.get("app", "?"),
            duration_ms=int((time.monotonic() - t0) * 1000),
            status=status,
        )
        self._set_state("IDLE", "")
