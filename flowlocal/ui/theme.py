"""FlowLocal visual theme — "recording studio at night".

Warm near-black surfaces, a single hot amber accent (the REC lamp), monospace
numerals for stats (VU-meter vibe). Applied app-wide as a QSS sheet.
"""

BG0 = "#16130F"      # window
BG1 = "#1E1A14"      # cards / panels
BG2 = "#28221A"      # hover / inputs
BORDER = "#37301F"
TEXT = "#EFE7D6"
MUTED = "#93876F"
AMBER = "#F5A623"    # accent — REC lamp amber
AMBER_DIM = "#7A5A1E"
REC = "#FF4D3A"      # recording red
OK = "#8FC98B"

DISPLAY_FONT = '"Segoe UI Variable Display", "Segoe UI", sans-serif'
BODY_FONT = '"Segoe UI Variable Text", "Segoe UI", sans-serif'
MONO_FONT = '"Cascadia Code", "Consolas", monospace'

QSS = f"""
* {{
    font-family: {BODY_FONT};
    font-size: 13px;
    color: {TEXT};
}}
QMainWindow, QWidget#Root {{
    background: {BG0};
}}

/* ---- sidebar -------------------------------------------------------- */
QWidget#Sidebar {{
    background: {BG1};
    border-right: 1px solid {BORDER};
}}
QLabel#Logo {{
    font-family: {DISPLAY_FONT};
    font-size: 19px;
    font-weight: 700;
    color: {TEXT};
    padding: 18px 16px 4px 16px;
}}
QLabel#LogoSub {{
    color: {MUTED};
    font-size: 11px;
    padding: 0 16px 14px 17px;
}}
QListWidget#Nav {{
    background: transparent;
    border: none;
    outline: none;
    padding: 4px 8px;
}}
QListWidget#Nav::item {{
    padding: 10px 12px;
    border-radius: 8px;
    margin: 2px 0;
    color: {MUTED};
}}
QListWidget#Nav::item:hover {{
    background: {BG2};
    color: {TEXT};
}}
QListWidget#Nav::item:selected {{
    background: {BG2};
    color: {AMBER};
    border-left: 3px solid {AMBER};
}}
QLabel#Version {{
    color: {MUTED};
    font-size: 11px;
    padding: 12px 16px;
}}

/* ---- cards & headings ------------------------------------------------ */
QLabel#PageTitle {{
    font-family: {DISPLAY_FONT};
    font-size: 24px;
    font-weight: 700;
    padding: 4px 0 2px 0;
}}
QLabel#PageHint {{
    color: {MUTED};
    padding-bottom: 8px;
}}
QFrame.Card {{
    background: {BG1};
    border: 1px solid {BORDER};
    border-radius: 12px;
}}
QLabel.StatValue {{
    font-family: {MONO_FONT};
    font-size: 34px;
    font-weight: 700;
    color: {AMBER};
}}
QLabel.StatLabel {{
    color: {MUTED};
    font-size: 12px;
    letter-spacing: 1px;
}}
QLabel.HeroState {{
    font-family: {DISPLAY_FONT};
    font-size: 20px;
    font-weight: 600;
}}
QGroupBox {{
    background: {BG1};
    border: 1px solid {BORDER};
    border-radius: 12px;
    margin-top: 12px;
    padding: 14px 10px 10px 10px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 4px;
    color: {AMBER};
}}

/* ---- inputs ----------------------------------------------------------- */
QLineEdit, QComboBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit {{
    background: {BG2};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 7px 10px;
    selection-background-color: {AMBER_DIM};
}}
QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus,
QPlainTextEdit:focus, QTextEdit:focus {{
    border: 1px solid {AMBER};
}}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {BG1};
    border: 1px solid {BORDER};
    selection-background-color: {BG2};
    selection-color: {AMBER};
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px; height: 16px;
}}
QCheckBox::indicator:unchecked, QRadioButton::indicator:unchecked {{
    border: 1px solid {MUTED};
    background: {BG2};
    border-radius: 4px;
}}
QRadioButton::indicator:unchecked {{ border-radius: 8px; }}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    border: 1px solid {AMBER};
    background: {AMBER};
    border-radius: 4px;
}}
QRadioButton::indicator:checked {{ border-radius: 8px; }}

/* ---- buttons ----------------------------------------------------------- */
QPushButton {{
    background: {BG2};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 8px 16px;
    font-weight: 600;
}}
QPushButton:hover {{ border-color: {AMBER}; color: {AMBER}; }}
QPushButton:pressed {{ background: {BG0}; }}
QPushButton#Primary {{
    background: {AMBER};
    color: {BG0};
    border: none;
}}
QPushButton#Primary:hover {{ background: #FFBD45; color: {BG0}; }}
QPushButton#Danger:hover {{ border-color: {REC}; color: {REC}; }}

/* ---- lists, tables, tabs, misc ---------------------------------------- */
QListWidget, QTableWidget {{
    background: {BG1};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 4px;
}}
QListWidget::item {{ padding: 8px; border-radius: 6px; }}
QListWidget::item:hover {{ background: {BG2}; }}
QListWidget::item:selected {{ background: {BG2}; color: {AMBER}; }}
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{
    background: transparent;
    color: {MUTED};
    padding: 8px 16px;
    border-bottom: 2px solid transparent;
    font-weight: 600;
}}
QTabBar::tab:selected {{ color: {AMBER}; border-bottom: 2px solid {AMBER}; }}
QSplitter::handle {{ background: {BORDER}; width: 1px; }}
QScrollBar:vertical {{
    background: transparent; width: 10px; margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {BG2}; border-radius: 5px; min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: {AMBER_DIM}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QToolTip {{
    background: {BG1}; color: {TEXT}; border: 1px solid {BORDER}; padding: 4px;
}}
"""
