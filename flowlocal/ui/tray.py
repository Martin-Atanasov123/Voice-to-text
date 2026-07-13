"""System tray icon + menu. Icon color mirrors pipeline state."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QBrush, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

STATE_COLORS = {
    "LOADING": QColor(150, 150, 150),
    "IDLE": QColor(70, 130, 240),
    "RECORDING": QColor(230, 60, 60),
    "TRANSCRIBING": QColor(240, 170, 40),
    "CLEANING": QColor(240, 170, 40),
    "PASTING": QColor(240, 170, 40),
    "PAUSED": QColor(110, 110, 110),
    "ERROR": QColor(230, 60, 60),
}


def _make_icon(color: QColor) -> QIcon:
    pm = QPixmap(32, 32)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(color))
    p.drawEllipse(4, 4, 24, 24)
    # simple mic slit to make it read as "voice"
    p.setBrush(QBrush(QColor(255, 255, 255, 230)))
    p.drawRoundedRect(13, 9, 6, 11, 3, 3)
    p.drawRect(15, 20, 2, 4)
    p.end()
    return QIcon(pm)


class Tray(QSystemTrayIcon):
    def __init__(self, on_pause, on_settings, on_history, on_quit, parent=None):
        super().__init__(parent)
        self._icons = {state: _make_icon(c) for state, c in STATE_COLORS.items()}
        self.setIcon(self._icons["LOADING"])
        self.setToolTip("FlowLocal — loading…")

        menu = QMenu()
        self._pause_action = QAction("Pause dictation")
        self._pause_action.triggered.connect(on_pause)
        menu.addAction(self._pause_action)
        menu.addSeparator()
        act_settings = QAction("Settings…")
        act_settings.triggered.connect(on_settings)
        menu.addAction(act_settings)
        act_history = QAction("History…")
        act_history.triggered.connect(on_history)
        menu.addAction(act_history)
        menu.addSeparator()
        act_quit = QAction("Quit")
        act_quit.triggered.connect(on_quit)
        menu.addAction(act_quit)
        self._menu = menu  # keep refs alive
        self._actions = [act_settings, act_history, act_quit]
        self.setContextMenu(menu)

    def set_state(self, state: str, detail: str) -> None:
        icon_state = state if state in self._icons else "IDLE"
        if state in ("BUSY", "WARNING"):
            icon_state = "IDLE"
        self.setIcon(self._icons[icon_state])
        tip = f"FlowLocal — {state.lower()}"
        if detail:
            tip += f" ({detail})"
        self.setToolTip(tip)
        self._pause_action.setText("Resume dictation" if state == "PAUSED" else "Pause dictation")
