"""Settings dashboard: General tab + Models & AI tab.

The Models tab shows live GPU info, hardware-based model recommendations,
the installed Ollama models, and the external-API backend option.
Whisper/backend changes take effect after an app restart (noted in the UI).
"""
import subprocess
import threading

import sounddevice as sd
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..cleanup import ApiCleaner, OllamaCleaner, list_ollama_models
from ..config import Config

WHISPER_MODELS = ["small", "medium", "large-v3-turbo"]
DEVICES = ["auto", "cuda", "cpu"]

# Ollama models worth suggesting for cleanup, by minimum system profile
RECOMMENDED_PULLS = [
    ("qwen2.5:3b-instruct", "EN cleanup — fast on CPU (~2GB)"),
    ("qwen3:4b-instruct-2507-q4_K_M", "BG cleanup — best small multilingual (~2.5GB)"),
    ("qwen2.5:7b-instruct", "Higher quality, needs 8GB+ VRAM or a fast CPU (~4.7GB)"),
]


def _gpu_info() -> dict | None:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.free", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        name, total, free = [x.strip() for x in out.stdout.strip().splitlines()[0].split(",")]
        return {"name": name, "total_mb": int(total), "free_mb": int(free)}
    except Exception:
        return None


def _recommendation_text(gpu: dict | None) -> str:
    if gpu is None:
        return (
            "No NVIDIA GPU detected.\n"
            "Recommended: whisper 'small' on CPU; cleanup with 3B-4B models on CPU."
        )
    total, free = gpu["total_mb"], gpu["free_mb"]
    lines = [f"GPU: {gpu['name']} — {total} MB total, {free} MB free right now."]
    if total <= 4096:
        lines.append(
            "Recommended for this card: whisper 'small' + device 'auto'. Your VRAM is "
            "usually taken by other apps, so CPU is the reliable path; 'auto' upgrades to "
            "large-v3-turbo on GPU automatically when ≥3000 MB is free at startup."
        )
        lines.append(
            "Cleanup: keep 3B (EN) / 4B (BG) models on CPU. 7B+ models will be too slow "
            "and do NOT fit this GPU."
        )
        if free >= 3000:
            lines.append("Right now enough VRAM is free — a restart would get you turbo on GPU.")
    elif total <= 8192:
        lines.append(
            "Recommended: whisper 'large-v3-turbo' + device 'auto' (fits when ~3GB free). "
            "Cleanup: up to 7B models."
        )
    else:
        lines.append(
            "Recommended: whisper 'large-v3-turbo' on GPU + 7B cleanup models — this card "
            "handles both."
        )
    return "\n".join(lines)


class _TestRunner(QObject):
    """Runs a cleanup test off the UI thread; result arrives as a queued signal."""

    done = Signal(str)

    def run(self, make_cleaner) -> None:
        def work():
            try:
                cleaner = make_cleaner()
                if not cleaner.health_check():
                    self.done.emit("✗ endpoint unreachable")
                    return
                out, ok = cleaner.clean("um this is a a test no wait a quick test", "en")
                self.done.emit(f"✓ {out}" if ok else f"✗ cleanup failed (raw returned): {out}")
            except Exception as e:
                self.done.emit(f"✗ {e}")

        threading.Thread(target=work, daemon=True).start()


class SettingsWindow(QWidget):
    def __init__(self, cfg: Config):
        super().__init__()
        self.cfg = cfg
        self.setWindowTitle("FlowLocal — Settings")
        self.resize(640, 560)

        tabs = QTabWidget()
        tabs.addTab(self._general_tab(), "General")
        tabs.addTab(self._models_tab(), "Models && AI")

        note = QLabel("Speech model, device and backend changes take effect after restarting FlowLocal.")
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
        lay.addWidget(tabs)
        lay.addWidget(note)
        lay.addLayout(btns)

    # -- General tab ---------------------------------------------------------
    def _general_tab(self) -> QWidget:
        cfg = self.cfg
        self._mic = QComboBox()
        self._mic.addItem("System default", None)
        for i, dev in enumerate(sd.query_devices()):
            if dev["max_input_channels"] > 0:
                self._mic.addItem(f"{dev['name']}", i)
        if cfg.mic_device is not None:
            idx = self._mic.findData(cfg.mic_device)
            if idx >= 0:
                self._mic.setCurrentIndex(idx)

        self._cleanup = QCheckBox("Clean up transcripts with AI")
        self._cleanup.setChecked(cfg.cleanup_enabled)
        self._timeout = QDoubleSpinBox(minimum=5, maximum=120, value=cfg.cleanup_timeout_s, suffix=" s")
        self._autostart = QCheckBox("Start with Windows")
        self._autostart.setChecked(cfg.autostart)

        form = QFormLayout()
        form.addRow("Microphone:", self._mic)
        form.addRow(self._cleanup)
        form.addRow("Cleanup timeout:", self._timeout)
        form.addRow(self._autostart)
        w = QWidget()
        w.setLayout(form)
        return w

    # -- Models & AI tab -------------------------------------------------------
    def _models_tab(self) -> QWidget:
        cfg = self.cfg
        gpu = _gpu_info()

        rec = QLabel(_recommendation_text(gpu))
        rec.setWordWrap(True)
        rec_box = QGroupBox("Hardware recommendation")
        rl = QVBoxLayout(rec_box)
        rl.addWidget(rec)

        # Speech (whisper)
        self._model = QComboBox()
        self._model.addItems(WHISPER_MODELS)
        self._model.setCurrentText(cfg.whisper_model)
        self._device = QComboBox()
        self._device.addItems(DEVICES)
        self._device.setCurrentText(cfg.whisper_device)
        speech_box = QGroupBox("Speech recognition (Whisper)")
        sf = QFormLayout(speech_box)
        sf.addRow("Model:", self._model)
        sf.addRow("Device:", self._device)

        # Local Ollama backend
        self._backend_ollama = QRadioButton("Local Ollama (private, offline)")
        self._backend_api = QRadioButton("External API (OpenAI-compatible)")
        (self._backend_api if cfg.cleanup_backend == "api" else self._backend_ollama).setChecked(True)

        installed = list_ollama_models(cfg.ollama_url)
        names = [m["name"] for m in installed]
        self._model_en = QComboBox(editable=True)
        self._model_bg = QComboBox(editable=True)
        for combo, current in ((self._model_en, cfg.ollama_model_en), (self._model_bg, cfg.ollama_model_bg)):
            combo.addItems(names)
            combo.setCurrentText(current)
        installed_label = (
            "Installed models: " + ", ".join(f"{m['name']} ({m['size_gb']} GB)" for m in installed)
            if installed
            else "Ollama unreachable — start it to list installed models."
        )
        pulls = "\n".join(f"•  ollama pull {name}   — {why}" for name, why in RECOMMENDED_PULLS)
        ollama_info = QLabel(installed_label + "\n\nGood models to install:\n" + pulls)
        ollama_info.setWordWrap(True)
        ollama_info.setStyleSheet("color: gray; font-size: 11px;")

        ollama_box = QGroupBox("Local cleanup models (Ollama)")
        of = QFormLayout(ollama_box)
        of.addRow("English model:", self._model_en)
        of.addRow("Bulgarian model:", self._model_bg)
        of.addRow(ollama_info)

        # API backend
        self._api_url = QLineEdit(cfg.api_base_url)
        self._api_url.setPlaceholderText("https://api.openai.com/v1")
        self._api_key = QLineEdit(cfg.api_key)
        self._api_key.setEchoMode(QLineEdit.Password)
        self._api_model = QLineEdit(cfg.api_model)
        self._api_model.setPlaceholderText("gpt-4o-mini")
        api_note = QLabel(
            "Works with any OpenAI-compatible endpoint (OpenAI, Groq, OpenRouter, Mistral, "
            "LM Studio…). Note: with an API, your dictated text leaves this PC."
        )
        api_note.setWordWrap(True)
        api_note.setStyleSheet("color: gray; font-size: 11px;")
        api_box = QGroupBox("External API")
        af = QFormLayout(api_box)
        af.addRow("Base URL:", self._api_url)
        af.addRow("API key:", self._api_key)
        af.addRow("Model:", self._api_model)
        af.addRow(api_note)

        # Test button
        self._test_result = QLabel("")
        self._test_result.setWordWrap(True)
        self._runner = _TestRunner()
        self._runner.done.connect(self._test_result.setText)
        test = QPushButton("Test selected backend")
        test.clicked.connect(self._test_backend)

        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(rec_box)
        lay.addWidget(speech_box)
        lay.addWidget(self._backend_ollama)
        lay.addWidget(ollama_box)
        lay.addWidget(self._backend_api)
        lay.addWidget(api_box)
        hl = QHBoxLayout()
        hl.addWidget(test)
        hl.addWidget(self._test_result, 1)
        lay.addLayout(hl)
        lay.addStretch(1)
        return w

    def _test_backend(self) -> None:
        self._test_result.setText("testing…")
        if self._backend_api.isChecked():
            url, key, model = self._api_url.text().strip(), self._api_key.text().strip(), self._api_model.text().strip()
            self._runner.run(lambda: ApiCleaner(url, key, model, 30))
        else:
            en, bg = self._model_en.currentText().strip(), self._model_bg.currentText().strip()
            self._runner.run(lambda: OllamaCleaner(self.cfg.ollama_url, {"en": en, "bg": bg}, 60))

    def _save(self) -> None:
        cfg = self.cfg
        cfg.mic_device = self._mic.currentData()
        cfg.cleanup_enabled = self._cleanup.isChecked()
        cfg.cleanup_timeout_s = self._timeout.value()
        cfg.whisper_model = self._model.currentText()
        cfg.whisper_device = self._device.currentText()
        cfg.cleanup_backend = "api" if self._backend_api.isChecked() else "ollama"
        cfg.ollama_model_en = self._model_en.currentText().strip()
        cfg.ollama_model_bg = self._model_bg.currentText().strip()
        cfg.api_base_url = self._api_url.text().strip()
        cfg.api_key = self._api_key.text().strip()
        cfg.api_model = self._api_model.text().strip()
        autostart_changed = cfg.autostart != self._autostart.isChecked()
        cfg.autostart = self._autostart.isChecked()
        cfg.save()
        if autostart_changed:
            from ..startup import set_autostart

            set_autostart(cfg.autostart)
        self.close()
