# FlowLocal v2 — Implementation Plan

Spec: [SPEC-v2.md](SPEC-v2.md). Scope confirmed after the user tested the 2026-07-22
fixes and reported Bulgarian now has "only very small problems" — so the large accuracy
workstream is **dropped**, leaving one targeted correctness fix.

## Context

v1.5 pastes text only after the key is released, with no feedback while speaking. v2 adds
a **live preview inside FlowLocal's own overlay** and improves release-to-paste speed,
without touching output quality: the pasted text still comes from a whole-utterance
transcription + cleanup pass, because self-corrections depend on seeing the full sentence.

Two constraints shape everything:
- One whisper model instance, ~1.1GB on a 4GB GPU. Preview and final pass **share** it
  and must be serialised.
- Preview must never delay or degrade the final result. If it can't keep up, it falls
  behind silently.

## M0 — Measurement spike (do this before any UI work)

The one real risk is that preview passes contend with the final pass and make paste
*slower* than v1.5. Settle it with numbers first.

Reuse the harness already written at
`%TEMP%\claude\...\scratchpad\bench_stt.py` (SAPI-generated speech, 11.8s sample).

Measure on the loaded turbo/cuda model:
- cost of transcribing a 2s / 3s / 4s tail chunk
- cost of the full-utterance pass for 10s / 30s / 60s of audio
- worst case added latency: a partial pass in flight at the moment of release

Baseline from 2026-07-22: turbo/cuda runs ~0.15s per second of audio (11.8s → 1.7–2.0s),
so a 3s chunk should cost ~0.45s.

**Kill criteria** — if a preview pass in flight adds more than ~0.5s to release-to-paste,
do not build the shared-model design. Fall back to previewing only every ~3s with a hard
"skip if release is imminent" rule, or drop live preview from v2.

## M1 — Partial transcription engine

**`flowlocal/audio.py`** — add `snapshot() -> np.ndarray`: concatenate the blocks captured
so far **without clearing them**. Copy the list reference first (`blocks = self._blocks[:]`)
so the audio callback can keep appending during the copy; do not take `_lock`, since the
callback never takes it either.

**`flowlocal/stt.py`** — add a `threading.Lock` guarding `self.model`, and
`transcribe_partial(audio, language)` that calls `_run` with `vad_filter=False` (VAD on a
2–3s fragment tends to swallow the whole thing — see the `VAD filter removed 00:07.046`
entries in the log). Both the partial and final paths must acquire the lock.

**`flowlocal/orchestrator.py`** —
- new signal `partial_text = Signal(str)` alongside `state_changed`
- `_do_start` starts a `preview` thread; `_do_finish`/`_do_cancel` clear a
  `threading.Event` to stop it
- preview loop: every ~1.2s, `recorder.snapshot()`, transcribe **only the newest ~3s**,
  append to a running preview string, `partial_text.emit(...)`
- `_do_finish` sets the stop flag **first**, then acquires the STT lock (waiting out any
  in-flight partial), then runs the existing full-audio `transcribe` unchanged

The worker thread is free during RECORDING (it blocks on `self._cmds.get()`), so preview
must run on its own thread — do not reuse the pipeline worker.

**`flowlocal/config.py`** — add `live_preview_enabled: bool = True` and
`preview_interval_s: float = 1.2`.

## M2 — Overlay preview UI

**`flowlocal/ui/overlay.py`** — currently a single-line pill whose `_on_pulse` recovers the
elapsed seconds by string-splitting the label text (`text.rsplit(" ", 1)[0]`). That breaks
the moment the label holds transcript text.

- store `self._elapsed_text` and `self._preview_text` as separate fields and rebuild the
  label from both, instead of parsing the rendered string
- add `set_partial(text: str)` slot; keep only the tail (~140 chars) so the pill stays a
  pill, enable word wrap and cap the width (~520px)
- `adjustSize()` + `_position()` on each update so it stays bottom-centred while growing
- clear preview text on IDLE/ERROR so nothing leaks into the next dictation

**`flowlocal/app.py`** — connect `self.orch.partial_text` to `self.overlay.set_partial`
next to the existing `state_changed` connections (queued automatically across threads).

## M3 — Bulgarian self-correction fix ✅ DONE (2026-07-22)

Investigated systematically before changing anything, which was worth it: **the bug as
originally reported did not exist**, and a worse one did.

- The failing test sentence was flawed. Bulgarian "не чакай" is both a self-correction
  marker and a literal imperative ("do not wait"), so the model keeping "вторник" was a
  legitimate parse. The models' own outputs gave it away — qwen2.5 split it into
  "Мисля… във вторник. **Не чакай** в сряда." and even conjugated "не чакай**те**".
- Both prompts were already at parity: `PROMPTS["bg"]` rule 2 matches the EN rule
  verbatim, so the planned "add the missing wording" fix would have been a no-op.
- All unambiguous BG markers (не, / извинявай / тоест / не, чакай,) passed 3/3 already.
- `qwen3:4b-instruct-2507` beat `qwen2.5:3b-instruct` on BG, confirming the current
  config — no model change needed.

**The real defect:** `FEW_SHOT["bg"]` used the ambiguous "не чакай" in its
self-correction example, teaching the model that "не чакай X" means *delete content*.
"тръгвай веднага не чакай автобуса" → "Тръгвай веднага." on 3/3 runs; "звънни ми утре не
чакай да ти пиша" → "Звънни ми утре." Fixed by switching the example to "извинявай",
keeping the stutter and counting-form lessons. Now 3/3 preserved, no regression on the
previously passing cases, EN untouched.

Regression test: **`tests/check_cleanup_bg.py`** (6 cases, exits non-zero on failure).

## M4 — Keep Ollama from breaking again

The models path was fixed on 2026-07-22, but the user's Startup shortcut still launches
`ollama app.exe`, which forces the bad `OLLAMA_MODELS`. If it wins the race for port
11434, cleanup silently dies again.

- `_preload` in `orchestrator.py` already calls the now model-aware `health_check()`.
  Extend the failure path: when the server is reachable but `missing_models()` is
  non-empty, attempt one restart of the server through `try_start_ollama()` before giving
  up, since we now know how to start it correctly.
- Offer to repoint the Startup shortcut at `ollama.exe serve` with a correct
  `OLLAMA_MODELS`. **Ask before touching it** — it is the user's own shortcut.
- Add the regression check to the verification list below.

## Verification

- Dictate EN and BG into Notepad, Chrome and Word: text appears in the overlay while
  speaking; the pasted result is the cleaned full-utterance version; clipboard restored.
- Compare release-to-paste against a v1.5 baseline on the same audio — must not regress.
- Self-correction phrases produce the corrected version in **both** languages (M3).
- Tap (short press) mid-preview cancels cleanly and leaves no preview text behind.
- Kill Ollama mid-session → raw text pasted with a warning, nothing lost.
- Start with Ollama's tray app already running → the app reports the real state instead
  of claiming health (regression test for the bug found on 2026-07-22).
- Dictate 60s → confirm the preview keeps up or degrades gracefully, and the final pass
  still produces one coherent transcript.

## Known limitation to accept

Long dictations stay slow at the end: the final pass re-transcribes the whole utterance
(~0.15s per second of audio, so ~9s for a 60s dictation). Reusing the partials to skip it
would cut this dramatically but costs accuracy at chunk boundaries — explicitly rejected
in the spec. Revisit only if long dictations turn out to be common in practice.
