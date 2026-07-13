# FlowLocal

Local Wispr Flow–style voice-to-text for Windows. **Hold CapsLock → speak → release** — cleaned-up text is pasted into whatever app has focus. 100% offline: Whisper for speech recognition, a local LLM (Ollama) for cleanup. English + Bulgarian, picked automatically from your current keyboard layout.

## Run

```
.venv\Scripts\python -m flowlocal
```

or double-click `run_flowlocal.pyw` (no console window). The tray icon turns **blue** when ready (~35s first warm-up), **red** while recording, **orange** while processing.

- **Hold CapsLock** and speak, release to finish. A quick tap does nothing (CapsLock toggle is disabled while FlowLocal runs; use Shift for capitals).
- **Select text anywhere + press Ctrl+CapsLock** → a popup offers Professional / Friendly /
  Shorter / Longer / Email / Fix grammar — the rewritten text replaces your selection.
  Works on any text in any app, not just dictations.
- **Smart context**: the dictation tone follows the focused app automatically — casual in
  Discord/Slack/Viber, polite email prose in Outlook, terse technical text in VS Code/
  terminals, polished prose in Word. Toggle in Settings → General.
- **Profiles & your style**: pick a profile (developer/student) and optionally paste a short
  sample of your own writing — cleanup leans toward your tone.
- Language: Windows keyboard layout at the moment you press (EN layout → English, BG layout → Bulgarian).
- Snippets support `{{date}}`, `{{time}}`, `{{day}}` placeholders, filled at paste time.
- If Ollama isn't running, dictations still work — raw transcript is pasted.

## Opening the app window / dashboard

On first run FlowLocal puts a **FlowLocal icon on your Desktop** — double-click it to start
the app. Once running, open the main window any of these ways:

- **Left-click the tray icon** (near the clock; check the **^ hidden icons** arrow if you
  don't see it) — opens the window on the Overview page.
- Right-click the tray icon → **Settings…** or **History…** jumps straight to that page.

The window has a sidebar with five pages:

- **Overview** — live status (Ready / Recording / …) and your stats: dictations, words
  spoken, dictations today, minutes saved vs typing.
- **History** — every dictation with raw + cleaned text, copy buttons, clear.
- **Dictionary** — names/terms that must always be spelled exactly right (they bias speech
  recognition AND are enforced during AI cleanup). Add e.g. product names, colleagues.
- **Snippets** — voice shortcuts: dictate exactly the cue phrase (e.g. "my signature") and
  the full stored text is pasted verbatim instead.
- **Settings** — two tabs: **General** (mic, cleanup on/off, timeout, autostart) and
  **Models & AI** (live GPU/VRAM info with hardware-based recommendation, per-language
  Ollama model pickers, external OpenAI-compatible API option with a test button).

Click **Save** in Settings to persist. Speech model/device and backend changes take effect
the *next time you start FlowLocal* (Quit from the tray menu, then start again). The API
option sends dictated text off this PC; local Ollama stays 100% offline.

**Closing the window does not quit the app** — it keeps listening in the tray. Quit only
via the tray menu.

If the window won't open, the app probably isn't running or crashed during the ~35s
startup — run `.venv\Scripts\python -m flowlocal` in a terminal to see any error.

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
