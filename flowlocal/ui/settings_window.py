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
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..cleanup import ApiCleaner, OllamaCleaner, list_ollama_models
from ..config import Config
from .. import keymap
from ..keymap import MODIFIER_VK
from ..stt import TURBO_VRAM_FREE_MB

WHISPER_MODELS = ["small", "medium", "large-v3-turbo"]
DEVICES = ["auto", "cuda", "cpu"]

def _encode_key(vk: int, extended: bool) -> str:
    return f"{vk}:{int(extended)}"


def _decode_key(s: str) -> tuple[int, bool]:
    vk, ext = s.split(":")
    return int(vk), bool(int(ext))


# Ollama models worth suggesting for cleanup, by minimum system profile.
# Sizes are approximate (default quantization on ollama.com) -- not independently
# re-verified here, since confirming them exactly would mean downloading each one.
RECOMMENDED_PULLS = [
    ("qwen2.5:3b-instruct", "EN cleanup — fast on CPU (~2GB)"),
    ("qwen3:4b-instruct-2507-q4_K_M", "BG cleanup — best small multilingual (~2.5GB)"),
    ("qwen2.5:7b-instruct", "Higher quality, needs 8GB+ VRAM or a fast CPU (~4.7GB)"),
    ("qwen2.5:14b-instruct", "Noticeably better cleanup, needs ~16GB+ VRAM (~9GB)"),
    ("qwen2.5:32b-instruct", "Near top-tier quality, needs ~24GB+ VRAM (~19GB)"),
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
            f"Recommended for this card: whisper 'small' + device 'auto'. Your VRAM is "
            f"usually taken by other apps, so CPU is the reliable path; 'auto' upgrades to "
            f"large-v3-turbo on GPU automatically when ≥{TURBO_VRAM_FREE_MB} MB is free "
            f"at startup."
        )
        lines.append(
            "Cleanup: keep 3B (EN) / 4B (BG) models on CPU. 7B+ models will be too slow "
            "and do NOT fit this GPU."
        )
        if free >= TURBO_VRAM_FREE_MB:
            lines.append("Right now enough VRAM is free — a restart would get you turbo on GPU.")
    elif total <= 8192:
        lines.append(
            "Recommended: whisper 'large-v3-turbo' + device 'auto'. "
            "Cleanup: up to 7B models."
        )
    elif total <= 16384:
        lines.append(
            "Recommended: whisper 'large-v3-turbo' on GPU. This card comfortably fits "
            "7B cleanup models on GPU too, for lower latency than CPU cleanup."
        )
    elif total <= 24576:
        lines.append(
            "Recommended: whisper 'large-v3-turbo' on GPU + a 14B cleanup model on GPU — "
            "this card has real headroom past what a 4-8GB card can do. See "
            "'Good models to install' below."
        )
    else:
        lines.append(
            "Recommended: whisper 'large-v3-turbo' on GPU + a 32B cleanup model on GPU — "
            "this card is well past the low-VRAM defaults this app ships with. See "
            "'Good models to install' below."
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
    # emitted from the hook's own thread when a key-capture completes;
    # Qt auto-queues delivery of _capture_finished onto this widget's thread
    key_captured = Signal(object, bool)

    def __init__(self, cfg: Config, capture_key_fn=None, hook=None):
        super().__init__()
        self.cfg = cfg
        self._capture_key_fn = capture_key_fn
        self._hook = hook
        self.key_captured.connect(self._capture_finished)
        self.setWindowTitle("FlowLocal — Settings")
        self.resize(640, 560)

        tabs = QTabWidget()
        tabs.addTab(self._general_tab(), "General")
        tabs.addTab(self._models_tab(), "Models && AI")
        tabs.addTab(self._hotkeys_tab(), "Hotkeys")

        note = QLabel(
            "Speech model, device and backend changes take effect after restarting FlowLocal. "
            "Hotkey changes apply immediately."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: gray;")

        save = QPushButton("Save")
        save.setObjectName("Primary")
        save.clicked.connect(self._save)
        self._saved_note = QLabel("")
        btns = QHBoxLayout()
        btns.addWidget(self._saved_note, 1)
        btns.addWidget(save)

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

        self._smart_context = QCheckBox(
            "Smart context — tone follows the app (chat casual, email polite, code technical)"
        )
        self._smart_context.setChecked(cfg.smart_context_enabled)
        self._clipboard_ai = QCheckBox(
            "Clipboard AI — offer Summarize/Translate/Explain after you copy text (restart to apply)"
        )
        self._clipboard_ai.setChecked(cfg.clipboard_ai_enabled)
        self._profile = QComboBox()
        self._profile.addItems(["general", "developer", "student"])
        self._profile.setCurrentText(cfg.profile)
        self._style = QPlainTextEdit(cfg.style_sample)
        self._style.setPlaceholderText(
            "Optional: paste a short sample of YOUR writing (an email, a message). "
            "Cleanup will lean toward your tone and habits. Max ~500 characters used."
        )
        self._style.setMaximumHeight(90)

        form = QFormLayout()
        form.addRow("Microphone:", self._mic)
        form.addRow(self._cleanup)
        form.addRow("Cleanup timeout:", self._timeout)
        form.addRow(self._autostart)
        form.addRow(self._smart_context)
        form.addRow(self._clipboard_ai)
        form.addRow("Profile:", self._profile)
        form.addRow("Your style sample:", self._style)
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

    # -- Hotkeys tab -----------------------------------------------------------
    # itemData is stored as a "vk:extended" STRING, never a raw tuple: PySide6's
    # QComboBox.findData() compares opaque Python objects by identity, not
    # value, so two equal-but-distinct tuples never match — strings compare
    # correctly (verified: the string-keyed modifier combos below never had
    # this problem).
    def _hotkeys_tab(self) -> QWidget:
        cfg = self.cfg

        self._ptt_combo = QComboBox()
        for vk, ext in keymap.RECOMMENDED_PTT_KEYS:
            self._ptt_combo.addItem(keymap.key_name(vk, ext), _encode_key(vk, ext))
        current = _encode_key(cfg.ptt_vk, cfg.ptt_extended)
        idx = self._ptt_combo.findData(current)
        if idx < 0:
            self._ptt_combo.addItem(f"Custom: {cfg.ptt_label}", current)
            idx = self._ptt_combo.count() - 1
        self._ptt_combo.setCurrentIndex(idx)

        self._ptt_capture_btn = QPushButton("Capture a different key…")
        self._ptt_capture_btn.clicked.connect(self._start_capture)
        self._ptt_status = QLabel("")
        self._ptt_status.setStyleSheet("color: gray;")

        ptt_row = QHBoxLayout()
        ptt_row.addWidget(self._ptt_combo, 1)
        ptt_row.addWidget(self._ptt_capture_btn)

        self._rewrite_mod = QComboBox()
        self._command_mod = QComboBox()
        for key, label in keymap.MODIFIER_CHOICES:
            self._rewrite_mod.addItem(label, key)
            self._command_mod.addItem(label, key)
        self._rewrite_mod.setCurrentIndex(self._rewrite_mod.findData(cfg.rewrite_modifier))
        self._command_mod.setCurrentIndex(self._command_mod.findData(cfg.command_modifier))

        self._hotkey_warning = QLabel("")
        self._hotkey_warning.setWordWrap(True)
        self._hotkey_warning.setStyleSheet("color: #E0703A;")

        reset = QPushButton("Reset to defaults (Caps Lock / Ctrl / Shift)")
        reset.clicked.connect(self._reset_hotkeys)

        hint = QLabel(
            "Hold the push-to-talk key to dictate. Hold it together with the Rewrite "
            "modifier over selected text to rewrite it; together with the Command "
            "modifier to dictate an instruction instead of text."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray;")

        form = QFormLayout()
        form.addRow(hint)
        form.addRow("Push-to-talk key:", ptt_row)
        form.addRow("", self._ptt_status)
        form.addRow("Rewrite modifier:", self._rewrite_mod)
        form.addRow("Command modifier:", self._command_mod)
        form.addRow(self._hotkey_warning)
        form.addRow(reset)

        for combo in (self._ptt_combo, self._rewrite_mod, self._command_mod):
            combo.currentIndexChanged.connect(self._check_hotkey_conflicts)
        self._check_hotkey_conflicts()

        w = QWidget()
        w.setLayout(form)
        return w

    def _start_capture(self) -> None:
        if self._capture_key_fn is None:
            self._ptt_status.setText("Capture unavailable — restart FlowLocal and try again.")
            return
        self._ptt_capture_btn.setEnabled(False)
        self._ptt_status.setText("Press any key… (Esc to cancel)")
        # the hook calls this back on ITS OWN thread; key_captured.emit() marshals
        # it onto the Qt main thread automatically (cross-thread signal emit)
        self._capture_key_fn(lambda vk, ext: self.key_captured.emit(vk, ext))

    def _capture_finished(self, vk, extended: bool) -> None:
        self._ptt_capture_btn.setEnabled(True)
        if vk is None:
            self._ptt_status.setText("Cancelled.")
            return
        vk = int(vk)
        label = keymap.key_name(vk, extended)
        key = _encode_key(vk, extended)
        idx = self._ptt_combo.findData(key)
        if idx < 0:
            # replace any previous "Custom" entry rather than piling up
            last = self._ptt_combo.count() - 1
            if last >= len(keymap.RECOMMENDED_PTT_KEYS):
                self._ptt_combo.removeItem(last)
            self._ptt_combo.addItem(f"Custom: {label}", key)
            idx = self._ptt_combo.count() - 1
        self._ptt_combo.setCurrentIndex(idx)
        self._ptt_status.setText(f"Captured: {label}")

    def _check_hotkey_conflicts(self) -> None:
        vk, _ext = _decode_key(self._ptt_combo.currentData())
        primary_family = keymap.key_family(vk)
        rw = self._rewrite_mod.currentData()
        cmd = self._command_mod.currentData()
        problems = []
        if primary_family is not None and primary_family == rw:
            problems.append(f"Push-to-talk key conflicts with the Rewrite modifier ({rw}).")
        if primary_family is not None and primary_family == cmd:
            problems.append(f"Push-to-talk key conflicts with the Command modifier ({cmd}).")
        if rw == cmd:
            problems.append("Rewrite and Command modifiers must be different.")
        self._hotkey_warning.setText("  •  ".join(problems))

    def _reset_hotkeys(self) -> None:
        self._ptt_combo.setCurrentIndex(self._ptt_combo.findData(_encode_key(*keymap.DEFAULT_PTT)))
        self._rewrite_mod.setCurrentIndex(
            self._rewrite_mod.findData(keymap.DEFAULT_REWRITE_MODIFIER)
        )
        self._command_mod.setCurrentIndex(
            self._command_mod.findData(keymap.DEFAULT_COMMAND_MODIFIER)
        )
        self._ptt_status.setText("Reset to defaults.")

    def _test_backend(self) -> None:
        self._test_result.setText("testing…")
        if self._backend_api.isChecked():
            url, key, model = self._api_url.text().strip(), self._api_key.text().strip(), self._api_model.text().strip()
            self._runner.run(lambda: ApiCleaner(url, key, model, 30))
        else:
            en, bg = self._model_en.currentText().strip(), self._model_bg.currentText().strip()
            self._runner.run(lambda: OllamaCleaner(self.cfg.ollama_url, {"en": en, "bg": bg}, 60))

    def _save(self) -> None:
        self._check_hotkey_conflicts()
        if self._hotkey_warning.text():
            self._saved_note.setText("Not saved — fix the hotkey conflict below first.")
            return

        cfg = self.cfg
        vk, ext = _decode_key(self._ptt_combo.currentData())
        cfg.ptt_vk = vk
        cfg.ptt_extended = ext
        cfg.ptt_label = keymap.key_name(vk, ext)
        cfg.rewrite_modifier = self._rewrite_mod.currentData()
        cfg.command_modifier = self._command_mod.currentData()
        if self._hook is not None:
            # live-apply so the new hotkey works immediately, no restart needed
            self._hook.primary_vk = vk
            self._hook.primary_extended = ext
            self._hook.rewrite_modifier_vk = MODIFIER_VK.get(cfg.rewrite_modifier, MODIFIER_VK["ctrl"])
            self._hook.command_modifier_vk = MODIFIER_VK.get(cfg.command_modifier, MODIFIER_VK["shift"])

        cfg.mic_device = self._mic.currentData()
        cfg.cleanup_enabled = self._cleanup.isChecked()
        cfg.cleanup_timeout_s = self._timeout.value()
        cfg.smart_context_enabled = self._smart_context.isChecked()
        cfg.clipboard_ai_enabled = self._clipboard_ai.isChecked()
        cfg.profile = self._profile.currentText()
        cfg.style_sample = self._style.toPlainText().strip()
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
        self._saved_note.setText(
            "Saved — hotkeys are active now. Speech model / backend changes apply after restarting FlowLocal."
        )
