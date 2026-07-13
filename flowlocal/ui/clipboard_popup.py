"""Clipboard AI surfaces: action popup after a copy + result viewer window.

The popup appears near the cursor without stealing focus and vanishes if
ignored — copying must never feel interrupted.
"""
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..clipboard_ai import ACTIONS
from . import theme


class ClipboardPopup(QWidget):
    action_chosen = Signal(str, str)  # (action key, copied text)

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
            f"QLabel {{ border: none; color: {theme.MUTED}; font-size: 11px; padding: 0 2px; }}"
            f"QPushButton {{ background: {theme.BG2}; border: 1px solid {theme.BORDER};"
            f" border-radius: 7px; padding: 6px 11px; font-weight: 600; font-size: 12px; }}"
            f"QPushButton:hover {{ border-color: {theme.AMBER}; color: {theme.AMBER}; }}"
        )
        self._text = ""
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 7, 10, 9)
        lay.setSpacing(6)
        lay.addWidget(QLabel("✨ AI on copied text"))
        row = QHBoxLayout()
        row.setSpacing(6)
        for key, (label, _instr) in ACTIONS.items():
            btn = QPushButton(label)
            btn.clicked.connect(lambda _=False, k=key: self._choose(k))
            row.addWidget(btn)
        lay.addLayout(row)
        self._auto_hide = QTimer(self, singleShot=True, timeout=self.hide)

    def offer(self, text: str) -> None:
        self._text = text
        self.adjustSize()
        pos = QCursor.pos()
        screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()
        x = min(pos.x() + 14, geo.right() - self.width() - 8)
        y = min(pos.y() + 18, geo.bottom() - self.height() - 8)
        self.move(max(geo.left() + 8, x), max(geo.top() + 8, y))
        self.show()
        self.raise_()
        self._auto_hide.start(5000)

    def _choose(self, key: str) -> None:
        self._auto_hide.stop()
        self.hide()
        self.action_chosen.emit(key, self._text)


class ResultViewer(QWidget):
    """Readable result of a clipboard action, with one-click copy."""

    def __init__(self):
        super().__init__(None, Qt.WindowStaysOnTopHint)
        self.setObjectName("Root")
        self.setWindowTitle("FlowLocal — result")
        self.resize(520, 340)

        self._title = QLabel("")
        self._title.setObjectName("PageTitle")
        self._body = QPlainTextEdit(readOnly=True)
        self._copy = QPushButton("Copy result")
        self._copy.setObjectName("Primary")
        self._copy.clicked.connect(self._do_copy)
        close = QPushButton("Close")
        close.clicked.connect(self.hide)

        btns = QHBoxLayout()
        btns.addStretch(1)
        btns.addWidget(self._copy)
        btns.addWidget(close)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 14, 20, 14)
        lay.addWidget(self._title)
        lay.addWidget(self._body, 1)
        lay.addLayout(btns)

    def present(self, title: str, text: str) -> None:
        self._title.setText(title)
        self._body.setPlainText(text)
        self._copy.setText("Copy result")
        self.show()
        self.raise_()
        self.activateWindow()

    def _do_copy(self) -> None:
        QGuiApplication.clipboard().setText(self._body.toPlainText())
        self._copy.setText("Copied ✓")
