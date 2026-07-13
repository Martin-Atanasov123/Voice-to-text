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
from .cleanup import create_cleaner
from .config import Config
from .history import History
from .inserter import (
    capture_selection,
    insert_text,
    paste_replacing_selection,
    restore_clipboard,
)
from .layout import get_dictation_language
from .context import tone_clause
from .personal import Dictionary, Snippets, profile_clause, render_snippet, style_clause
from .rewrite import STYLES, detect_language
from .stt import Transcriber

log = logging.getLogger(__name__)

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


from .context import foreground_exe as _foreground_exe  # noqa: E402


class Orchestrator(QObject):
    # state name + human detail; UI (overlay/tray) renders from this alone
    state_changed = Signal(str, str)
    # selection captured, ready for the style popup (app shows RewritePopup)
    rewrite_ready = Signal()

    def __init__(self, cfg: Config):
        super().__init__()
        self.cfg = cfg
        self.state = "LOADING"
        self._state_lock = threading.Lock()
        self.recorder = Recorder(cfg.mic_device, cfg.max_record_s)
        self.stt = Transcriber(cfg.whisper_model, cfg.whisper_device, cfg.whisper_model_hq, cfg.beam_size)
        self.cleaner = create_cleaner(cfg)
        self.history = History()
        self.dictionary = Dictionary()
        self.snippets = Snippets()
        self.ollama_ok = False
        self._cmds: queue.Queue = queue.Queue()
        self._worker = threading.Thread(target=self._run, name="pipeline", daemon=True)
        self._ctx: dict = {}
        self._rw: dict | None = None  # pending rewrite: text, saved clipboard, hwnd

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
            detail += " — cleanup unavailable, will paste raw text"
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

    def on_combo(self) -> None:
        """Ctrl+CapsLock from the hook thread: rewrite the current selection."""
        with self._state_lock:
            if self.state != "IDLE":
                return
        self._cmds.put(("rewrite_capture", None))

    def choose_rewrite_style(self, style_key: str) -> None:
        self._cmds.put(("rewrite_run", style_key))

    def cancel_rewrite(self) -> None:
        self._cmds.put(("rewrite_cancel", None))

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
                elif cmd == "rewrite_capture":
                    self._do_rewrite_capture()
                elif cmd == "rewrite_run":
                    self._do_rewrite_run(arg)
                elif cmd == "rewrite_cancel":
                    self._do_rewrite_cancel()
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

    # -- rewrite-on-demand ---------------------------------------------------
    def _do_rewrite_capture(self) -> None:
        hwnd = user32.GetForegroundWindow()
        text, saved = capture_selection()
        if not text or not text.strip():
            restore_clipboard(saved)
            self._flash("WARNING", "no text selected")
            return
        self._rw = {"text": text, "saved": saved, "hwnd": hwnd, "t0": time.monotonic(),
                    "app": _foreground_exe()}
        self.rewrite_ready.emit()

    def _do_rewrite_run(self, style_key: str) -> None:
        rw, self._rw = self._rw, None
        if rw is None or style_key not in STYLES:
            return
        lang = detect_language(rw["text"])
        self._set_state("CLEANING", f"rewriting ({STYLES[style_key][0].lower()})…")
        result, ok = self.cleaner.transform(rw["text"], STYLES[style_key][1], lang)
        if not ok:
            restore_clipboard(rw["saved"])
            self._flash("ERROR", "rewrite failed — selection unchanged")
            self._set_state("IDLE", "")
            return
        self._set_state("PASTING", "")
        try:
            user32.SetForegroundWindow(rw["hwnd"])  # focus back on the target app
            time.sleep(0.15)
            paste_replacing_selection(result, rw["saved"])
        except Exception as e:
            log.warning("rewrite paste failed: %s", e)
            restore_clipboard(rw["saved"])
            self._flash("ERROR", "paste failed — text is in history")
        self.history.add(
            language=lang,
            raw_text=rw["text"],
            cleaned_text=result,
            target_app=rw.get("app", "?"),
            duration_ms=int((time.monotonic() - rw["t0"]) * 1000),
            status=f"rewrite:{style_key}",
        )
        self._set_state("IDLE", "")

    def _do_rewrite_cancel(self) -> None:
        rw, self._rw = self._rw, None
        if rw is not None:
            restore_clipboard(rw["saved"])

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
        raw = self.stt.transcribe(audio, lang, hotwords=self.dictionary.hotwords())
        if not raw:
            self._flash("WARNING", "didn't catch that")
            self._set_state("IDLE", "")
            return

        snippet = self.snippets.match(raw)
        if snippet is not None:
            text, status = render_snippet(snippet), "snippet"
        else:
            text, status = raw, "cleanup_off"
            if self.cfg.cleanup_enabled:
                self._set_state("CLEANING", "")
                extra = self.dictionary.prompt_clause(lang)
                if self.cfg.smart_context_enabled:
                    extra += tone_clause(self._ctx.get("app", "?"), lang)
                extra += profile_clause(self.cfg.profile, lang)
                extra += style_clause(self.cfg.style_sample, lang)
                cleaned, ok = self.cleaner.clean(raw, lang, extra)
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
            cleaned_text=text if status in ("cleaned", "snippet") else None,
            target_app=self._ctx.get("app", "?"),
            duration_ms=int((time.monotonic() - t0) * 1000),
            status=status,
        )
        self._set_state("IDLE", "")
