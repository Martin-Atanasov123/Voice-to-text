"""Rewrite style picker: small popup at the cursor after Ctrl+CapsLock.

Shown WITHOUT stealing focus (the selection in the target app must survive);
buttons are still clickable. Auto-hides if ignored.
"""
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from ..rewrite import STYLES
from . import theme


class RewritePopup(QWidget):
    style_chosen = Signal(str)
    dismissed = Signal()

    def __init__(self):
        super().__init__(
            None,
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setStyleSheet(
            f"QWidget {{ background: {theme.BG1}; border: 1px solid {theme.BORDER};"
            f" border-radius: 10px; }}"
            f"QLabel {{ border: none; color: {theme.MUTED}; font-size: 11px;"
            f" padding: 2px 4px; }}"
            f"QPushButton {{ background: {theme.BG2}; border: 1px solid {theme.BORDER};"
            f" border-radius: 7px; padding: 7px 14px; text-align: left; font-weight: 600; }}"
            f"QPushButton:hover {{ border-color: {theme.AMBER}; color: {theme.AMBER}; }}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 10)
        lay.setSpacing(5)
        lay.addWidget(QLabel("Rewrite selection as…"))
        for key, (label, _instr) in STYLES.items():
            btn = QPushButton(label)
            btn.clicked.connect(lambda _=False, k=key: self._choose(k))
            lay.addWidget(btn)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self._dismiss)
        lay.addWidget(cancel)

        self._auto_hide = QTimer(self, singleShot=True, timeout=self._dismiss)

    def show_at_cursor(self) -> None:
        self.adjustSize()
        pos = QCursor.pos()
        screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()
        x = min(pos.x() + 12, geo.right() - self.width() - 8)
        y = min(pos.y() + 12, geo.bottom() - self.height() - 8)
        self.move(max(geo.left() + 8, x), max(geo.top() + 8, y))
        self.show()
        self.raise_()
        self._auto_hide.start(12000)

    def _choose(self, key: str) -> None:
        self._auto_hide.stop()
        self.hide()
        self.style_chosen.emit(key)

    def _dismiss(self) -> None:
        self._auto_hide.stop()
        if self.isVisible():
            self.hide()
            self.dismissed.emit()
