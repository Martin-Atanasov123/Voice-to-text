"""Dictation history browser: list on the left, raw/cleaned detail on the right."""
from datetime import datetime

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication

from ..history import History


class HistoryWindow(QWidget):
    def __init__(self, history: History):
        super().__init__()
        self.history = history
        self.setWindowTitle("FlowLocal — History")
        self.resize(760, 460)
        self._rows: list[tuple] = []

        self._list = QListWidget()
        self._list.currentRowChanged.connect(self._show_row)

        self._meta = QLabel("")
        self._meta.setWordWrap(True)
        self._raw = QPlainTextEdit(readOnly=True)
        self._cleaned = QPlainTextEdit(readOnly=True)
        copy_raw = QPushButton("Copy raw")
        copy_raw.clicked.connect(lambda: self._copy(self._raw))
        copy_cleaned = QPushButton("Copy cleaned")
        copy_cleaned.clicked.connect(lambda: self._copy(self._cleaned))
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        clear = QPushButton("Clear history")
        clear.clicked.connect(self._clear)

        right = QWidget()
        rlay = QVBoxLayout(right)
        rlay.addWidget(self._meta)
        rlay.addWidget(QLabel("Cleaned:"))
        rlay.addWidget(self._cleaned, 2)
        rlay.addWidget(QLabel("Raw transcript:"))
        rlay.addWidget(self._raw, 1)
        btns = QHBoxLayout()
        for b in (copy_cleaned, copy_raw, refresh, clear):
            btns.addWidget(b)
        rlay.addLayout(btns)

        split = QSplitter(Qt.Horizontal)
        split.addWidget(self._list)
        split.addWidget(right)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 2)
        lay = QVBoxLayout(self)
        lay.addWidget(split)

    def refresh(self) -> None:
        self._rows = self.history.recent()
        self._list.clear()
        for _id, ts, lang, raw, cleaned, app, _dur, status in self._rows:
            when = datetime.fromtimestamp(ts).strftime("%d %b %H:%M")
            preview = (cleaned or raw).replace("\n", " ")[:48]
            item = QListWidgetItem(f"{when}  [{lang}]  {preview}")
            if status in ("raw_fallback", "error"):
                item.setToolTip(f"status: {status}")
            self._list.addItem(item)
        if self._rows:
            self._list.setCurrentRow(0)

    def _show_row(self, row: int) -> None:
        if row < 0 or row >= len(self._rows):
            return
        _id, ts, lang, raw, cleaned, app, dur, status = self._rows[row]
        when = datetime.fromtimestamp(ts).strftime("%d %B %Y %H:%M:%S")
        self._meta.setText(f"{when} — {lang} — into {app} — {dur} ms — {status}")
        self._raw.setPlainText(raw or "")
        self._cleaned.setPlainText(cleaned or "(no cleaned version)")

    def _copy(self, edit: QPlainTextEdit) -> None:
        QGuiApplication.clipboard().setText(edit.toPlainText())

    def _clear(self) -> None:
        self.history.clear()
        self.refresh()
