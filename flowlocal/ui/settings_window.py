"""Settings window backed by Config. Changes persist to config.json on Save.

Most changes apply on next dictation; whisper model/device changes need an
app restart (kept simple for v1 — noted in the window).
"""
import sounddevice as sd
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..config import Config

WHISPER_MODELS = ["small", "medium", "large-v3-turbo"]
DEVICES = ["auto", "cuda", "cpu"]


class SettingsWindow(QWidget):
    def __init__(self, cfg: Config):
        super().__init__()
        self.cfg = cfg
        self.setWindowTitle("FlowLocal — Settings")
        self.resize(460, 380)

        self._mic = QComboBox()
        self._mic.addItem("System default", None)
        for i, dev in enumerate(sd.query_devices()):
            if dev["max_input_channels"] > 0:
                self._mic.addItem(f"{dev['name']}", i)
        if cfg.mic_device is not None:
            idx = self._mic.findData(cfg.mic_device)
            if idx >= 0:
                self._mic.setCurrentIndex(idx)

        self._model = QComboBox()
        self._model.addItems(WHISPER_MODELS)
        self._model.setCurrentText(cfg.whisper_model)
        self._device = QComboBox()
        self._device.addItems(DEVICES)
        self._device.setCurrentText(cfg.whisper_device)

        self._cleanup = QCheckBox("Clean up transcripts with local AI (Ollama)")
        self._cleanup.setChecked(cfg.cleanup_enabled)
        self._model_en = QLineEdit(cfg.ollama_model_en)
        self._model_bg = QLineEdit(cfg.ollama_model_bg)
        self._timeout = QDoubleSpinBox(minimum=5, maximum=120, value=cfg.cleanup_timeout_s, suffix=" s")

        self._autostart = QCheckBox("Start with Windows")
        self._autostart.setChecked(cfg.autostart)

        form = QFormLayout()
        form.addRow("Microphone:", self._mic)
        form.addRow("Speech model:", self._model)
        form.addRow("Compute device:", self._device)
        form.addRow(self._cleanup)
        form.addRow("Cleanup model (EN):", self._model_en)
        form.addRow("Cleanup model (BG):", self._model_bg)
        form.addRow("Cleanup timeout:", self._timeout)
        form.addRow(self._autostart)

        note = QLabel("Speech model/device changes take effect after restarting FlowLocal.")
        note.setWordWrap(True)
        note.setStyleSheet("color: gray;")

        save = QPushButton("Save")
        save.clicked.connect(self._save)
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        btns = QHBoxLayout()
        btns.addStretch(1)
        btns.addWidget(save)
        btns.addWidget(close)

        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(note)
        lay.addStretch(1)
        lay.addLayout(btns)

    def _save(self) -> None:
        self.cfg.mic_device = self._mic.currentData()
        self.cfg.whisper_model = self._model.currentText()
        self.cfg.whisper_device = self._device.currentText()
        self.cfg.cleanup_enabled = self._cleanup.isChecked()
        self.cfg.ollama_model_en = self._model_en.text().strip()
        self.cfg.ollama_model_bg = self._model_bg.text().strip()
        self.cfg.cleanup_timeout_s = self._timeout.value()
        autostart_changed = self.cfg.autostart != self._autostart.isChecked()
        self.cfg.autostart = self._autostart.isChecked()
        self.cfg.save()
        if autostart_changed:
            from ..startup import set_autostart

            set_autostart(self.cfg.autostart)
        self.close()
