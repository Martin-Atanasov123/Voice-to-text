"""FlowLocal main window: sidebar navigation + pages.

Pages: Overview (live status + stats), History, Dictionary, Snippets,
Settings (General / Models & AI tabs). Opened from the desktop icon,
tray left-click, or tray menu.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..config import Config
from ..personal import Dictionary, Snippets
from .history_window import HistoryWindow
from .settings_window import SettingsWindow
from . import theme

NAV_ITEMS = [
    ("◉", "Overview"),
    ("≡", "History"),
    ("Aa", "Dictionary"),
    ("⚡", "Snippets"),
    ("⚙", "Settings"),
]

STATE_TEXT = {
    "LOADING": ("Loading models…", theme.MUTED),
    "IDLE": ("Ready — hold CapsLock and speak", theme.OK),
    "RECORDING": ("● Recording…", theme.REC),
    "TRANSCRIBING": ("Transcribing…", theme.AMBER),
    "CLEANING": ("Cleaning up…", theme.AMBER),
    "PASTING": ("Pasting…", theme.AMBER),
    "PAUSED": ("Paused — CapsLock works normally", theme.MUTED),
    "ERROR": ("Error", theme.REC),
}


def _card(inner: QWidget) -> QFrame:
    frame = QFrame()
    frame.setProperty("class", "Card")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(18, 14, 18, 14)
    lay.addWidget(inner)
    return frame


class OverviewPage(QWidget):
    def __init__(self, history):
        super().__init__()
        self.history = history

        title = QLabel("Overview")
        title.setObjectName("PageTitle")
        hint = QLabel("Your voice, everywhere on this PC — fully local.")
        hint.setObjectName("PageHint")

        self._state = QLabel("Loading models…")
        self._state.setProperty("class", "HeroState")
        self._state.setStyleSheet(f"color: {theme.MUTED};")
        hero_inner = QWidget()
        hl = QVBoxLayout(hero_inner)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.addWidget(self._state)
        sub = QLabel("Hold CapsLock → speak → release. Quick tap does nothing.")
        sub.setStyleSheet(f"color: {theme.MUTED};")
        hl.addWidget(sub)
        self._hero = _card(hero_inner)

        self._stat_labels: dict[str, QLabel] = {}
        grid = QGridLayout()
        grid.setSpacing(12)
        for col, (key, label) in enumerate(
            [("dictations", "DICTATIONS"), ("words", "WORDS SPOKEN"),
             ("today", "TODAY"), ("minutes_saved", "MINUTES SAVED")]
        ):
            value = QLabel("0")
            value.setProperty("class", "StatValue")
            caption = QLabel(label)
            caption.setProperty("class", "StatLabel")
            inner = QWidget()
            il = QVBoxLayout(inner)
            il.setContentsMargins(0, 0, 0, 0)
            il.addWidget(value)
            il.addWidget(caption)
            grid.addWidget(_card(inner), 0, col)
            self._stat_labels[key] = value

        self._langs = QLabel("")
        self._langs.setStyleSheet(f"color: {theme.MUTED};")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 22, 28, 22)
        lay.addWidget(title)
        lay.addWidget(hint)
        lay.addWidget(self._hero)
        lay.addSpacing(6)
        lay.addLayout(grid)
        lay.addSpacing(4)
        lay.addWidget(self._langs)
        lay.addStretch(1)

    def set_state(self, state: str, detail: str) -> None:
        text, color = STATE_TEXT.get(state, (state.title(), theme.MUTED))
        if state == "ERROR" and detail:
            text = f"Error: {detail}"
        self._state.setText(text)
        self._state.setStyleSheet(f"color: {color};")

    def refresh(self) -> None:
        s = self.history.stats()
        for key, label in self._stat_labels.items():
            label.setText(f"{s[key]:,}")
        if s["by_lang"]:
            parts = ", ".join(f"{k.upper()}: {v}" for k, v in sorted(s["by_lang"].items()))
            self._langs.setText(f"By language — {parts}.   Minutes saved assumes typing at 40 WPM.")


class DictionaryPage(QWidget):
    def __init__(self, dictionary: Dictionary):
        super().__init__()
        self.dictionary = dictionary

        title = QLabel("Dictionary")
        title.setObjectName("PageTitle")
        hint = QLabel(
            "Names and terms that must always be spelled exactly right — they bias speech "
            "recognition and are enforced during AI cleanup. E.g. product names, colleagues, brands."
        )
        hint.setObjectName("PageHint")
        hint.setWordWrap(True)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Add a term (e.g. Supabase, Атанасов, FlowLocal)…")
        self._input.returnPressed.connect(self._add)
        add = QPushButton("Add")
        add.setObjectName("Primary")
        add.clicked.connect(self._add)
        row = QHBoxLayout()
        row.addWidget(self._input, 1)
        row.addWidget(add)

        self._list = QListWidget()
        remove = QPushButton("Remove selected")
        remove.setObjectName("Danger")
        remove.clicked.connect(self._remove)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 22, 28, 22)
        lay.addWidget(title)
        lay.addWidget(hint)
        lay.addLayout(row)
        lay.addWidget(self._list, 1)
        lay.addWidget(remove, 0, Qt.AlignRight)
        self.refresh()

    def refresh(self) -> None:
        self._list.clear()
        self._list.addItems(self.dictionary.terms)

    def _add(self) -> None:
        self.dictionary.add(self._input.text())
        self._input.clear()
        self.refresh()

    def _remove(self) -> None:
        item = self._list.currentItem()
        if item:
            self.dictionary.remove(item.text())
            self.refresh()


class SnippetsPage(QWidget):
    def __init__(self, snippets: Snippets):
        super().__init__()
        self.snippets = snippets

        title = QLabel("Snippets")
        title.setObjectName("PageTitle")
        hint = QLabel(
            "Voice shortcuts: dictate exactly the cue phrase and the full text is pasted "
            "instead. Great for email signatures, addresses, links you say often."
        )
        hint.setObjectName("PageHint")
        hint.setWordWrap(True)

        self._cue = QLineEdit()
        self._cue.setPlaceholderText("Spoken cue (e.g. 'my signature' / 'моят подпис')")
        self._text = QPlainTextEdit()
        self._text.setPlaceholderText("Full text to paste when you say the cue…")
        self._text.setMaximumHeight(110)
        save = QPushButton("Save snippet")
        save.setObjectName("Primary")
        save.clicked.connect(self._save)

        self._list = QListWidget()
        self._list.currentTextChanged.connect(self._load_selected)
        remove = QPushButton("Remove selected")
        remove.setObjectName("Danger")
        remove.clicked.connect(self._remove)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 22, 28, 22)
        lay.addWidget(title)
        lay.addWidget(hint)
        lay.addWidget(self._cue)
        lay.addWidget(self._text)
        lay.addWidget(save, 0, Qt.AlignRight)
        lay.addWidget(self._list, 1)
        lay.addWidget(remove, 0, Qt.AlignRight)
        self.refresh()

    def refresh(self) -> None:
        self._list.clear()
        self._list.addItems(sorted(self.snippets.items))

    def _load_selected(self, cue: str) -> None:
        if cue in self.snippets.items:
            self._cue.setText(cue)
            self._text.setPlainText(self.snippets.items[cue])

    def _save(self) -> None:
        self.snippets.set(self._cue.text(), self._text.toPlainText().strip())
        self.refresh()

    def _remove(self) -> None:
        item = self._list.currentItem()
        if item:
            self.snippets.remove(item.text())
            self.refresh()


class MainWindow(QWidget):
    PAGE_OVERVIEW, PAGE_HISTORY, PAGE_DICTIONARY, PAGE_SNIPPETS, PAGE_SETTINGS = range(5)

    def __init__(self, cfg: Config, orch):
        super().__init__()
        self.setObjectName("Root")
        self.setWindowTitle("FlowLocal")
        self.resize(960, 640)

        logo = QLabel("◉ FlowLocal")
        logo.setObjectName("Logo")
        logo_sub = QLabel("local voice-to-text")
        logo_sub.setObjectName("LogoSub")
        self._nav = QListWidget()
        self._nav.setObjectName("Nav")
        for glyph, label in NAV_ITEMS:
            self._nav.addItem(f"  {glyph}   {label}")
        version = QLabel(f"v{__version__}")
        version.setObjectName("Version")

        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(208)
        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.addWidget(logo)
        sl.addWidget(logo_sub)
        sl.addWidget(self._nav, 1)
        sl.addWidget(version)

        self.overview = OverviewPage(orch.history)
        self.history_page = HistoryWindow(orch.history)
        self.dictionary_page = DictionaryPage(orch.dictionary)
        self.snippets_page = SnippetsPage(orch.snippets)
        self.settings_page = SettingsWindow(cfg)

        self._pages = QStackedWidget()
        for page in (self.overview, self.history_page, self.dictionary_page,
                     self.snippets_page, self.settings_page):
            self._pages.addWidget(page)

        self._nav.currentRowChanged.connect(self._switch)
        self._nav.setCurrentRow(0)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(sidebar)
        lay.addWidget(self._pages, 1)

    def _switch(self, row: int) -> None:
        self._pages.setCurrentIndex(row)
        if row == self.PAGE_OVERVIEW:
            self.overview.refresh()
        elif row == self.PAGE_HISTORY:
            self.history_page.refresh()

    def open_page(self, row: int) -> None:
        self._nav.setCurrentRow(row)
        self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowMinimized)
        self.raise_()
        self.activateWindow()

    def set_state(self, state: str, detail: str) -> None:
        self.overview.set_state(state, detail)

    def closeEvent(self, event) -> None:
        # closing the window never quits the app — it lives in the tray
        event.ignore()
        self.hide()
