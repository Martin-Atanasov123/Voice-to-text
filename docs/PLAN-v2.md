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

## M4 — Keep Ollama from breaking again (next up)

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

- Self-correction phrases produce the corrected version in **both** languages (M3) —
  covered by `tests/check_cleanup_bg.py`.
- Kill Ollama mid-session → raw text pasted with a warning, nothing lost.
- Start with Ollama's tray app already running → the app reports the real state instead
  of claiming health (regression test for the bug found on 2026-07-22).
