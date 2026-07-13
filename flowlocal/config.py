"""App configuration: dataclass persisted as JSON in %APPDATA%\\FlowLocal\\config.json."""
import dataclasses
import json
import os
from dataclasses import dataclass
from pathlib import Path

APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "FlowLocal"
CONFIG_PATH = APP_DIR / "config.json"


@dataclass
class Config:
    mic_device: int | None = None          # None = system default input
    # Benchmarked 2026-07-12 on the GTX 1650 (VRAM ~80% occupied by other apps):
    # small/cpu beam1 = 2.6s per 11s audio; turbo/cuda thrashes (44-197s) unless
    # ~3GB VRAM is actually free. "auto" probes free VRAM and picks accordingly.
    whisper_model: str = "small"
    whisper_model_hq: str = "large-v3-turbo"  # used by auto mode when VRAM allows
    whisper_device: str = "auto"           # auto | cuda | cpu
    beam_size: int = 1
    ollama_url: str = "http://localhost:11434"
    # Per-language cleanup models: qwen2.5:3b is fast and perfect for EN but
    # mangles Bulgarian; qwen3:4b handles BG correctly (slower on CPU).
    ollama_model_en: str = "qwen2.5:3b-instruct"
    ollama_model_bg: str = "qwen3:4b-instruct-2507-q4_K_M"
    # Cleanup backend: "ollama" (local) or "api" (any OpenAI-compatible endpoint).
    # api_key lives in config.json in %APPDATA% — local file, plain text.
    cleanup_backend: str = "ollama"
    api_base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    api_model: str = "gpt-4o-mini"
    # v1.3: context-aware dictation
    smart_context_enabled: bool = True     # tone follows the focused app
    profile: str = "general"               # general | developer | student
    style_sample: str = ""                 # short sample of the user's writing style
    # v1.4: clipboard AI popup after every copy (Summarize/Translate/Explain/Grammar)
    clipboard_ai_enabled: bool = True
    cleanup_enabled: bool = True
    cleanup_timeout_s: float = 20.0
    tap_threshold_s: float = 0.3
    max_record_s: float = 120.0
    # Hotkeys — defaults preserved here so "Reset to defaults" always works
    # even after the user changes them: CapsLock hold / Ctrl+ / Shift+.
    ptt_vk: int = 0x14              # CapsLock
    ptt_extended: bool = False
    ptt_label: str = "Caps Lock"
    rewrite_modifier: str = "ctrl"
    command_modifier: str = "shift"
    autostart: bool = True
    overlay_position: str = "bottom-center"

    @classmethod
    def load(cls) -> "Config":
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            known = {f.name for f in dataclasses.fields(cls)}
            return cls(**{k: v for k, v in data.items() if k in known})
        except (FileNotFoundError, json.JSONDecodeError, TypeError):
            return cls()

    def save(self) -> None:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(
            json.dumps(dataclasses.asdict(self), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
