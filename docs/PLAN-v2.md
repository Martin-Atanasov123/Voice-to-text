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

## M0 — Measurement spike ✅ DONE (2026-07-23)

Measured with a 49.8s SAPI speech sample, FlowLocal stopped so the GPU was clean.
**Verdict: live preview is affordable — but NOT with the shared-model design this plan
originally proposed.**

### The assumption that broke

A preview pass on turbo/cuda costs **~1.6s regardless of chunk length**:

| tail chunk | 2s | 3s | 4s |
|---|---|---|---|
| cost | 1.64s | 1.61s | 1.62s |

The predicted ~0.45s for a 3s chunk (extrapolated from 0.15s per second of audio) was
wrong. Whisper always encodes a fixed 30-second window, so a 2s clip pays nearly the same
encoder cost as a 30s one; only decoding scales with the number of words. Shrinking the
chunk buys nothing.

Consequences for the shared-model design: each preview pass is *slower than the 1.2s
interval* between passes, the model ends up busy ~57% of the time, and a pass in flight
at the moment of release costs the final pass a full lock wait.

| design | added release-to-paste latency |
|---|---|
| shared model + lock, forced worst case | **+1.66s** ❌ (limit 0.50s) |
| separate `tiny`/cpu preview model | **+0.18s** ✅ |

### Design decision

**Preview runs on its own `tiny` model on CPU.** No lock, no shared state, so there is no
worst-case spike at all — the +0.18s is only CPU contention. A 3s tail costs 0.39–0.43s,
comfortably faster than the preview interval, and produces usable text
("hold up well enough to show externally."). VRAM is untouched; `tiny` int8 is ~75MB RAM.

### Reference numbers (turbo/cuda, final pass, vad_filter=True)

| audio | 10s | 30s | 49s |
|---|---|---|---|
| pass | 1.73s | 3.61s | 3.93s |
| per second | 0.173s | 0.120s | 0.080s |

## M1 — Partial transcription engine

**`flowlocal/audio.py`** — add `snapshot() -> np.ndarray`: concatenate the blocks captured
so far **without clearing them**. Copy the list reference first (`blocks = self._blocks[:]`)
so the audio callback can keep appending during the copy; do not take `_lock`, since the
callback never takes it either.

**`flowlocal/stt.py`** — add a separate `PreviewTranscriber` holding its own
`WhisperModel("tiny", device="cpu", compute_type="int8")`, with
`transcribe_partial(audio, language)` calling `transcribe` with `vad_filter=False` (VAD on
a 2–3s fragment tends to swallow the whole thing — see the `VAD filter removed 00:07.046`
entries in the log). **No lock is needed anywhere**: preview and final pass use different
model objects on different devices. Do not add a lock "just in case" — M0 measured the
locked design at +1.66s.

**`flowlocal/orchestrator.py`** —
- new signal `partial_text = Signal(str)` alongside `state_changed`
- `_do_start` starts a `preview` thread; `_do_finish`/`_do_cancel` clear a
  `threading.Event` to stop it
- preview loop: every ~1.2s, `recorder.snapshot()`, transcribe **only the newest ~3s** on
  the preview model, append to a running preview string, `partial_text.emit(...)`
- `_do_finish` stops the preview thread and runs the existing full-audio `transcribe`
  unchanged — it never waits for preview work
- load the preview model in `_preload`, after the main model, so a failure there degrades
  to "no preview" rather than "no dictation"

The worker thread is free during RECORDING (it blocks on `self._cmds.get()`), so preview
must run on its own thread — do not reuse the pipeline worker.

**`flowlocal/config.py`** — add `live_preview_enabled: bool = True`,
`preview_model: str = "tiny"` and `preview_interval_s: float = 1.2`.

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
