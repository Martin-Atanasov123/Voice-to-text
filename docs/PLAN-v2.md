# FlowLocal v2 — Implementation Plan

Spec: [SPEC-v2.md](SPEC-v2.md).

## Context

Live preview while speaking was explored and **rejected by the user on 2026-07-23**: it
only adds a cosmetic "here's what I'm hearing" indicator during the hold — the text that
actually gets pasted was never going to change — and the investigation showed it would
require two extra models, a language-dependent chunking strategy, and non-trivial new
failure modes, for a feature the current hold→speak→release→paste flow doesn't need. Full
spike data (M0/M1 measurements, the Bulgarian tiny-vs-base experiment) stays in git
history (`825dc07`, `8357b32`) if a future session wants to revisit it — nothing here
carries it forward.

With that dropped, v2 shrinks to the one confirmed correctness fix plus one open
reliability gap, both already scoped in [SPEC-v2.md](SPEC-v2.md).

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

## M4 — Keep Ollama from breaking again ✅ DONE (2026-07-23)

The models path was fixed on 2026-07-22, but the user's Startup shortcut still launched
`ollama app.exe`, which forces the bad `OLLAMA_MODELS`. If it won the race for port
11434, cleanup would silently die again.

**Race condition in `_preload()`, fixed.** `app.py`'s `run()` already tries to auto-start
Ollama in a background thread when unhealthy (`_try_recover_ollama`), but
`orchestrator._preload()` ran its OWN one-shot `health_check()` in parallel — if that
landed before recovery finished starting Ollama, `ollama_ok` latched `False` for the rest
of the session even though Ollama came up moments later. `_preload` now calls
`_wait_for_cleanup_ready()`, which retries `health_check()` for up to 15s (matching
`_try_recover_ollama`'s own window) before giving up, giving the parallel recovery attempt
a real chance to land. Verified: normal healthy startup is unaffected (single check
succeeds immediately, no added delay).

**Startup shortcut: detect + offer to fix, never silent.** Verified first (important,
changed the design): a bare `ollama.exe serve` with **no** `OLLAMA_MODELS` override at all
correctly defaults to `<home>/.ollama/models` — the bug is specific to the tray app's own
wrapper, not Ollama itself. So the fix is to repoint the shortcut at the CLI directly, not
to inject an env var (which a `.lnk` can't hold anyway).

- `cleanup.py`: `ollama_startup_shortcut()` detects whether `Startup\Ollama.lnk` points at
  `ollama app.exe`; `fix_ollama_startup_shortcut()` repoints it at `ollama.exe serve`.
- `app.py`: `_offer_shortcut_fix()` shows a `QMessageBox` (Yes/No, default No) explaining
  the trade-off — fixes the model-folder bug for good, but the user loses the Ollama tray
  icon at login since FlowLocal starts Ollama itself anyway. Asked **at most once, ever**
  regardless of the answer (`cfg.ollama_shortcut_fix_asked`), never touches the shortcut
  without that explicit confirmation.
- **Caught and fixed a real regression while wiring this in**: the first version called
  `_offer_shortcut_fix()` synchronously before `orch.start()`/`hook.start()` — since
  `QMessageBox.question()` blocks the calling function until dismissed, this meant the
  *entire app*, including the CapsLock hook, would not become live until the one-time
  dialog was answered. Confirmed by testing: `flowlocal.log` stayed completely empty after
  launch. Fixed by starting the hook/orchestrator first and deferring the dialog via
  `QTimer.singleShot(0, ...)` so it fires only after dictation is already fully live.
  Reverified: `state: IDLE` (hook + whisper + cleanup all up) is reached with the process
  fully responsive, regardless of whether the dialog has been answered yet.

Verified against the real, currently-broken shortcut on this machine (detection correctly
found it); the actual repoint was left for the user to accept or decline via the real
one-time dialog on their own next restart, rather than triggered by this investigation.

## Verification

- Self-correction phrases produce the corrected version in **both** languages (M3) —
  covered by `tests/check_cleanup_bg.py`.
- Kill Ollama mid-session → raw text pasted with a warning, nothing lost.
- Start with Ollama's tray app already running → the app reports the real state instead
  of claiming health (regression test for the bug found on 2026-07-22).
- Fresh launch reaches `state: IDLE` (dictation-ready) whether or not the one-time
  shortcut-fix dialog has been answered yet (M4 regression test — this broke once).
- Accepting the shortcut-fix dialog repoints `Startup\Ollama.lnk` at `ollama.exe serve`;
  declining leaves it untouched either way, and it is never asked again.

## v2 status

M3 and M4 are both done. No further items are currently planned — the live-preview
feature that originally motivated this plan was dropped by the user (see Context above).
Revisit this doc when a new v2-scale piece of work is proposed.
