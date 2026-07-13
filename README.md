# FlowLocal

Local Wispr Flow–style voice-to-text for Windows. **Hold CapsLock → speak → release** — cleaned-up text is pasted into whatever app has focus. 100% offline: Whisper for speech recognition, a local LLM (Ollama) for cleanup. English + Bulgarian, picked automatically from your current keyboard layout.

## Run

```
.venv\Scripts\python -m flowlocal
```

or double-click `run_flowlocal.pyw` (no console window). The tray icon turns **blue** when ready (~35s first warm-up), **red** while recording, **orange** while processing.

- **Hold CapsLock** and speak, release to finish. A quick tap does nothing (CapsLock toggle is disabled while FlowLocal runs; use Shift for capitals).
- Language: Windows keyboard layout at the moment you press (EN layout → English, BG layout → Bulgarian).
- Tray menu: Pause/Resume (CapsLock works normally while paused), Settings, History, Quit.
- If Ollama isn't running, dictations still work — raw transcript is pasted.
- Settings → "Models & AI" dashboard: live GPU info with model recommendations for your
  hardware, pick installed Ollama models per language, or switch cleanup to any
  OpenAI-compatible API (OpenAI, Groq, OpenRouter, LM Studio…) with a built-in test button.
  Note: the API option sends dictated text off this PC; local Ollama stays 100% offline.

## Requirements

- Windows 11, Python 3.13, [Ollama](https://ollama.com) with models:
  `ollama pull qwen2.5:3b-instruct` (EN cleanup) and `ollama pull qwen3:4b-instruct-2507-q4_K_M` (BG cleanup)
- `pip install -r requirements.txt` into `.venv`

## Design notes

- Speech: faster-whisper `small` int8 on CPU by default — benchmarked fastest on this
  machine because the GTX 1650's 4GB VRAM is usually occupied; `auto` device upgrades to
  `large-v3-turbo` on GPU when ≥3GB VRAM is actually free at startup.
- Cleanup LLMs run CPU-only (`num_gpu: 0`) so they never fight Whisper for VRAM.
- Known v1 limitations: text-only clipboard restore; no paste into elevated (admin) windows;
  cleanup adds seconds (quality-first by design — disable in Settings for instant raw paste).

Docs: [docs/SPEC.md](docs/SPEC.md) (product spec), [docs/PLAN.md](docs/PLAN.md) (implementation plan).
