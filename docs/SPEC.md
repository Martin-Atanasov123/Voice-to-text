# FlowLocal — Local Voice-to-Text for Windows (Wispr Flow clone)

## Context
The user hates typing and wants a **fully local**, Wispr Flow–style dictation tool for Windows: hold a key, speak, release, and polished text appears in whatever app has focus (browser, Word, Discord, IDE, etc.). Nothing leaves the PC. This spec was produced through a structured interview; the implementation plan will be written after the user confirms the spec.

## Spec Summary

### Product
- **What:** System-tray Windows app. Hold **CapsLock** → record mic → release → transcribe locally (Whisper) → clean up locally (small LLM via Ollama) → paste into the focused app via clipboard.
- **User:** Single user (the owner), personal tool, Windows 11, GTX 1650 (4GB VRAM).
- **Quality bar:** "Understand me as well as possible" — quality-first: every dictation goes through LLM cleanup; user accepts ~2–5s post-release latency.

### Core flow (the only flow)
1. App runs in tray (auto-starts with Windows).
2. User holds CapsLock (tap <~0.3s = ignored; CapsLock toggling is fully hijacked/disabled).
3. Small floating overlay appears: recording indicator/waveform.
4. User releases → overlay shows "processing…".
5. Audio → **faster-whisper** (GPU, int8) → raw transcript, language selected by **current Windows keyboard layout** (EN or BG, one language per dictation).
6. Raw transcript → **Ollama** small instruct model (CPU-friendly, ~3B) with a cleanup prompt: remove fillers (umm / ами / значи…), fix grammar & punctuation, apply self-corrections ("Tuesday… no wait, Wednesday" → "Wednesday"), preserve meaning and language.
7. Cleaned text → clipboard → simulate Ctrl+V → restore previous clipboard.
8. Dictation (raw + cleaned + timestamp + app name) saved to local history (SQLite).

### Scope — IN (v1)
- Push-to-talk via CapsLock (global low-level keyboard hook; suppress CapsLock toggle).
- Local STT: faster-whisper, default **large-v3-turbo int8** on GPU (fits 4GB), fallback to medium/small; EN + BG.
- Language from active Windows keyboard layout at record start.
- Local LLM cleanup via Ollama (always on; raw-paste fallback on failure).
- Clipboard-paste insertion with clipboard save/restore.
- Overlay indicator (recording / processing / error states).
- Tray icon + menu (pause, open settings, open history, quit).
- Settings window (mic device, model choice, cleanup on/off, hotkey later).
- Dictation history window (browse, copy, raw vs cleaned).
- Run at Windows startup; runs from Python env + startup shortcut (no .exe packaging).
- Failure behavior: cleanup fails → paste RAW + brief warning; transcription fails → overlay error, paste nothing; words are never silently lost.

### Scope — OUT (v1)
- Streaming/live transcript while speaking.
- Personal dictionary / custom vocabulary.
- Spoken formatting commands ("new paragraph", "bullet list").
- Mixed-language within one dictation; auto language detection.
- Tone matching per app, translations, wake word, macOS/Linux, cloud anything, .exe packaging, multi-user.

### Data model (local only)
- `history` (SQLite): id, timestamp, language, raw_text, cleaned_text, target_app, duration_ms, status.
- `config` (TOML/JSON file): mic device, whisper model, ollama model, cleanup enabled, autostart, overlay position.
- No accounts, no auth, no network besides localhost Ollama.

### Architecture (Python)
- **Hotkey module:** low-level WH_KEYBOARD_LL hook (e.g. via `keyboard` lib or ctypes) — detects CapsLock hold/release, suppresses toggle.
- **Audio module:** `sounddevice` mic capture, 16kHz mono ring buffer.
- **STT module:** `faster-whisper` (CTranslate2, CUDA int8).
- **Cleanup module:** HTTP to local Ollama (`/api/chat`), strict prompt, timeout → raw fallback.
- **Inserter:** `pywin32`/`pyperclip` clipboard save→set→Ctrl+V→restore.
- **UI:** tray (`pystray`) + overlay/settings/history (likely PySide6 or tkinter — decided in implementation plan).
- **Orchestrator:** state machine IDLE → RECORDING → TRANSCRIBING → CLEANING → PASTING → IDLE; worker threads so hook thread never blocks; queue = drop-new (one dictation at a time).

## ASSUMPTIONS (user gave no firm answer — defaults chosen)
1. Whisper model: **large-v3-turbo int8** as default (best BG accuracy that fits 4GB); auto-fallback if VRAM insufficient.
2. Cleanup LLM: **Qwen2.5 3B instruct** via Ollama (good multilingual incl. BG, runs acceptably on CPU); swappable in settings.
3. Mic: Windows default input device (changeable in settings).
4. Only two layouts matter: EN + BG; any other layout defaults to English.
5. Max dictation length ~2 minutes per hold (memory cap); overlay warns near limit.
6. Overlay position: bottom-center of active monitor.
7. History retention: unlimited until user clears (local disk is cheap).
8. Ollama is installed by the user once; app checks at startup and shows guidance if missing.
9. Exact library versions to be verified against current docs during implementation planning (per user rule: no version guessing).

## OPEN RISKS
1. **CapsLock suppression** is the riskiest bit: reliably swallowing the toggle while detecting hold/release needs a low-level hook; some apps/anti-cheat may interfere. Mitigation: proven `keyboard`-lib pattern + fallback hotkey option.
2. **4GB VRAM ceiling:** large-v3-turbo int8 + CUDA runtime should fit, but other GPU apps (browser, games) may steal VRAM → OOM. Mitigation: auto-fallback to medium/small int8, or CPU.
3. **Bulgarian cleanup quality** of a 3B model is unproven — grammar fixes in BG may be mediocre. Mitigation: language-specific prompts; test early; allow "cleanup off per language".
4. **First-dictation latency:** model load takes ~10–30s at app start; needs warm preloading and a "loading" tray state.
5. **Clipboard race conditions:** apps that are slow to process Ctrl+V before clipboard restore → paste the wrong thing. Mitigation: small delay + verify; known solvable.
6. **Paste-blocked targets** (some terminals, games): out of scope for v1, typing fallback deferred to v2.
7. cuDNN/CUDA setup pain on Windows for CTranslate2 — must pin correct wheel/DLL versions during implementation.

## Verification (how we'll know v1 works)
- Dictate EN and BG into Notepad, Chrome textbox, Word: correct language, cleaned text, original clipboard restored.
- Filler/self-correction test phrases produce expected cleaned output.
- Kill Ollama mid-run → raw text pasted + warning.
- Reboot → app auto-starts, first dictation works after warm-up.

---
*Implementation plan (milestones, file layout, exact library versions) to be added after user confirms this spec.*
