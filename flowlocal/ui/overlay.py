"""Floating status pill: frameless, always-on-top, click-through.

Rendered states (from Orchestrator.state_changed):
  RECORDING  red pulsing dot + elapsed seconds
  TRANSCRIBING / CLEANING / PASTING  spinner text
  BUSY / WARNING  amber flash (auto-hide)
  ERROR  red flash (auto-hide)
  IDLE / PAUSED  hidden
"""
from PySide6.QtCore import Qt, QTimer, QTime
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

COLORS = {
    "record": QColor(230, 60, 60),
    "work": QColor(70, 130, 240),
    "warn": QColor(240, 170, 40),
    "error": QColor(230, 60, 60),
    "bg": QColor(28, 28, 32, 235),
    "text": QColor(240, 240, 245),
}

WORK_LABELS = {
    "TRANSCRIBING": "transcribing…",
    "CLEANING": "cleaning up…",
    "PASTING": "pasting…",
    "LOADING": "loading…",
}


class Overlay(QWidget):
    def __init__(self):
        super().__init__(
            None,
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowTransparentForInput
            | Qt.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self._label = QLabel("")
        self._label.setStyleSheet("color: rgb(240,240,245); font-size: 13px; font-family: 'Segoe UI';")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(30, 8, 16, 8)  # left margin leaves room for the dot
        lay.addWidget(self._label)

        self._mode = "hidden"  # hidden | record | work | flash
        self._dot_on = True
        self._record_started: QTime | None = None

        self._pulse = QTimer(self, interval=500, timeout=self._on_pulse)
        self._hide_timer = QTimer(self, singleShot=True, timeout=self._end_flash)
        self._prev = None  # (mode, text) to restore after a flash

    # -- public ------------------------------------------------------------
    def set_state(self, state: str, detail: str) -> None:
        if state == "RECORDING":
            self._record_started = QTime.currentTime()
            lang = detail.upper() if detail else ""
            self._show("record", f"listening {lang}  0s")
        elif state in WORK_LABELS and state != "LOADING":
            self._show("work", WORK_LABELS[state])
        elif state in ("BUSY", "WARNING"):
            self._flash("warn", detail or state.lower())
        elif state == "ERROR":
            self._flash("error", detail or "error")
        else:  # IDLE, PAUSED, LOADING
            self._mode = "hidden"
            self._pulse.stop()
            self.hide()

    # -- internals -----------------------------------------------------------
    def _show(self, mode: str, text: str) -> None:
        self._mode = mode
        self._label.setText(text)
        if mode == "record" and not self._pulse.isActive():
            self._pulse.start()
        elif mode != "record":
            self._pulse.stop()
        self.adjustSize()
        self._position()
        self.show()
        self.update()

    def _flash(self, mode: str, text: str) -> None:
        if self._mode in ("record", "work"):
            self._prev = (self._mode, self._label.text())
        else:
            self._prev = None
        self._show(mode, text)
        self._hide_timer.start(1800)

    def _end_flash(self) -> None:
        if self._prev:
            self._show(*self._prev)
            self._prev = None
        else:
            self._mode = "hidden"
            self.hide()

    def _on_pulse(self) -> None:
        self._dot_on = not self._dot_on
        if self._mode == "record" and self._record_started is not None:
            secs = self._record_started.secsTo(QTime.currentTime())
            text = self._label.text()
            base = text.rsplit(" ", 1)[0]
            self._label.setText(f"{base} {secs}s")
        self.update()

    def _position(self) -> None:
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()
        x = geo.center().x() - self.width() // 2
        y = geo.bottom() - self.height() - 60
        self.move(x, y)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(COLORS["bg"])
        p.drawRoundedRect(self.rect(), self.height() / 2, self.height() / 2)
        color = {
            "record": COLORS["record"],
            "work": COLORS["work"],
            "warn": COLORS["warn"],
            "error": COLORS["error"],
        }.get(self._mode)
        if color is not None:
            if self._mode == "record" and not self._dot_on:
                color = QColor(color)
                color.setAlpha(70)
            p.setBrush(color)
            r = 5
            p.drawEllipse(self.rect().left() + 12, self.rect().center().y() - r, 2 * r, 2 * r)
