# FlowLocal

Local Wispr Flow–style voice-to-text for Windows. **Hold CapsLock → speak → release** — cleaned-up text is pasted into whatever app has focus. 100% offline: Whisper for speech recognition, a local LLM (Ollama) for cleanup. English + Bulgarian, picked automatically from your current keyboard layout.

## Run

```
.venv\Scripts\python -m flowlocal
```

or double-click `run_flowlocal.pyw` (no console window). The tray icon turns **blue** when ready (~35s first warm-up), **red** while recording, **orange** while processing.

- **Hold CapsLock** and speak, release to finish. A quick tap does nothing (CapsLock toggle is disabled while FlowLocal runs; use Shift for capitals).
- Language: Windows keyboard layout at the moment you press (EN layout → English, BG layout → Bulgarian).
- If Ollama isn't running, dictations still work — raw transcript is pasted.

## Opening the Settings / Models & AI dashboard

FlowLocal has **no regular window** — it lives only in the Windows system tray (the small icons
near the clock, bottom-right of your screen). To open the dashboard:

1. **Start the app first** (see "Run" above) and wait for the tray icon to turn **blue** —
   that means it's ready. There is no separate "dashboard" program to launch; it's a window
   inside the running app.
2. Look at the tray icons next to the clock. If you don't see the FlowLocal icon (a small
   circle with a microphone shape), click the **^ "Show hidden icons"** arrow — Windows
   often hides new tray icons there. You can drag it out next to the clock so it's always visible.
3. **Right-click** the FlowLocal tray icon. A menu appears with: Pause/Resume dictation,
   **Settings…**, History…, Quit.
4. Click **Settings…** — a window opens with two tabs: **General** and **Models & AI**.
5. Click the **Models & AI** tab — this is the "dashboard": live GPU/VRAM info with a
   hardware-based recommendation, dropdowns to pick the Ollama model used for English and
   for Bulgarian cleanup (from what's already installed), a switch to use an external API
   instead of local Ollama (Base URL, API key, model name), and a **"Test selected backend"**
   button to confirm it works before saving.
6. Change what you want, then click **Save** at the bottom (or **Close** to discard).
   Note: changing the speech model/device or the cleanup backend only takes effect the
   *next time you start FlowLocal* — quit it from the tray menu and run it again.
   Note: switching to an external API sends your dictated text off this PC; local Ollama
   stays 100% offline.

If nothing appears when you right-click, the app probably isn't running yet, or crashed
during the ~35s startup — check by running it from a terminal (`.venv\Scripts\python -m
flowlocal`) so you can see any error printed there.

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
