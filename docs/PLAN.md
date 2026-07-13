# FlowLocal — Local Voice-to-Text for Windows (v1 plan)

Wispr Flow–style dictation, 100% local. Hold CapsLock → speak → release → Whisper
transcribes (GPU) → local LLM cleans up (Ollama) → text pasted into the focused app.

Full spec/interview record: see `docs/SPEC.md`.

## Verified stack (2026-07-12)

- Python 3.13 venv (`.venv`)
- faster-whisper 1.2.1, model `large-v3-turbo` int8 — fallback chain:
  turbo/cuda/int8 → small/cuda/int8 → turbo/cpu/int8
- ctranslate2 4.8.1 (CUDA 12 + cuDNN 9 via `nvidia-cublas-cu12` / `nvidia-cudnn-cu12`
  pip wheels; `os.add_dll_directory()` on their `bin` dirs BEFORE importing faster_whisper)
- Ollama (user has v0.24.0 installed), cleanup model `qwen2.5:3b-instruct`,
  `POST /api/chat`, `keep_alive: "30m"`, 20s timeout → raw fallback
- PySide6 6.11.1 (tray = QSystemTrayIcon, overlay = frameless click-through, settings, history)
- sounddevice 0.5.5 (16kHz mono float32), pywin32 312 (clipboard + SendInput)
- Keyboard hook: own ctypes WH_KEYBOARD_LL (the `keyboard` lib is unmaintained)
- Language: active keyboard layout of foreground window — 0x0409→en, 0x0402→bg, else en

## Architecture

```
flowlocal/
  __main__.py      # entry; cuda_setup FIRST, then app
  app.py           # QApplication wiring
  config.py        # %APPDATA%\FlowLocal\config.json
  cuda_setup.py    # nvidia DLL dirs
  hotkey.py        # WH_KEYBOARD_LL hook thread (CapsLock hold/release, suppress toggle)
  audio.py         # sounddevice recorder
  layout.py        # keyboard-layout → language
  stt.py           # faster-whisper + fallback chain
  cleanup.py       # Ollama client, EN+BG prompts
  inserter.py      # clipboard save → paste → restore
  history.py       # SQLite %APPDATA%\FlowLocal\history.db
  orchestrator.py  # state machine + pipeline worker thread
  ui/ overlay.py tray.py settings_window.py history_window.py
```

State machine: LOADING → IDLE ⇄ RECORDING → TRANSCRIBING → CLEANING → PASTING → IDLE,
plus PAUSED and transient ERROR. Single in-flight dictation (queue maxsize=1, drop-new).
Tap <0.3s ignored; ~2 min recording cap. Cleanup failure → paste RAW + warning;
transcription failure → overlay error, paste nothing.

Threading: Qt main thread owns all widgets; hook thread does microseconds of work only;
pipeline worker (STT→cleanup→paste) talks to UI via Qt signals; preload thread warms
Whisper + Ollama at startup.

## Milestones

- **M0 Spikes**: `spikes/spike_hook.py` (CapsLock suppression) + `spikes/spike_stt.py`
  (turbo int8 on GTX 1650, EN+BG). Do not proceed until both pass.
- **M1 Headless pipeline**: hold→speak→release→RAW text pasted; clipboard restored.
- **M2 Cleanup**: Ollama integration, per-language prompts, raw fallback on failure.
- **M3 Qt shell**: tray + overlay + orchestrator threading.
- **M4 History + Settings** windows, config persistence.
- **M5 Startup**: shell:startup shortcut, single-instance mutex, warm preload, polish.

## Pitfalls (encode in code)

1. DLL dirs before faster_whisper import (else "cudnn_ops64_9.dll not found").
2. LL hook proc must be allocation-free (<300ms budget) and the HOOKPROC object
   must be referenced at module level (GC crash otherwise).
3. Ignore LLKHF_INJECTED (our own SendInput must not re-enter the hook).
4. Dedupe CapsLock auto-repeat (track is-down flag).
5. Non-elevated process: no hook/paste into elevated windows — document, never auto-elevate.
6. Widgets only on main thread; cross-thread via signals.
7. OpenClipboard retry loops; 300ms grace before restore; CF_UNICODETEXT only (v1 restores text-only clipboard).
8. Wait for physical Shift/Alt/Win release before injecting Ctrl+V.
9. Wrap transcribe() in try/except and walk fallback chain at inference time too
   (VRAM can be stolen after startup — user's GPU often sits at 3.2/4GB used).
10. Ollama keep_alive + startup warm-up to avoid 5–15s cold starts.
