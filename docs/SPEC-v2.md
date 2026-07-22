# FlowLocal v2 — Spec

## Context

FlowLocal v1.5 works: dictation, rewrite-on-selection, Command Mode, Clipboard AI,
dictionary, snippets, profiles, configurable hotkeys. This spec covers v2, produced
through a structured interview on 2026-07-22.

The interview started from three stated complaints — **missing Wispr Flow features,
speed, and accuracy in both languages**. Diagnosis showed the accuracy complaint had a
different cause than assumed (see "What the diagnosis changed"), and the one proposed
new feature — live preview while speaking — was explored, found to add real complexity
(two extra models, language-dependent chunking) for a purely cosmetic benefit, and
**rejected by the user on 2026-07-23**: it doesn't change what gets pasted, only adds a
"here's what I'm hearing" indicator during the hold, and the existing hold→speak→
release→paste flow already works well without it.

That leaves v2 as: the accuracy/reliability fixes already investigated, plus one
open reliability gap.

## Spec Summary

### Product & users
- Unchanged: single-user, Windows, fully local, tray app. Same core gesture, same UI —
  **no new feature in v2**.
- **v2 targets the owner's machine only.** Public release is explicitly **v3**.
- Long-term direction (decided, not built in v2): replace the Ollama dependency
  with **inference bundled into the app** (llama.cpp/GGUF), because no ordinary
  user will install Ollama and pull models by hand. New cleanup work goes behind the
  existing `_BaseCleaner` interface in `cleanup.py`, which already abstracts backends via
  `create_cleaner(cfg)`.

### Speed
- The hard "<1s after release" target was **withdrawn during the interview** in favour of
  quality, then the whole speed workstream became moot once GPU transcription was fixed
  (see below) and live preview was dropped — there is no remaining speed work in v2.

### Accuracy
- Largely resolved by fixes already applied: dead cleanup revived, GPU model unlocked,
  and the Bulgarian self-correction defect fixed (see Risks — M3, done).

### Out of scope for v2
- Live preview / streaming text while speaking — **explicitly rejected**, not deferred.
- Automatic language detection / mixed language within one dictation.
- Spoken formatting commands ("new paragraph", "bullet list").
- Languages beyond EN/BG.
- Packaging, installer, code signing, onboarding, multi-user, monetization — all v3.
- Replacing Ollama with bundled inference (direction is set; work is v3).

## What the diagnosis changed

Investigated during the interview, fixed and committed as `2641a9c`:

1. **Cleanup had been dead for ~10 days.** Ollama's tray app starts the server with
   `OLLAMA_MODELS` pointing at the home directory instead of `~/.ollama/models`. The
   server answered as healthy while holding zero models, so every cleanup 404'd and
   silently pasted raw text. 14.63GB of models were on disk the whole time.
2. **`health_check()` was why nobody noticed** — it only pinged `/api/version`, so the
   above counted as healthy. It now verifies the configured models exist.
3. **The GPU model was almost never used.** The `TURBO_VRAM_FREE_MB = 3000` gate came
   from a thrashing measurement taken at ~800MB free. Re-benchmarked with an 11.8s
   speech sample at ~2700MB free: `large-v3-turbo/cuda` occupies only ~1.1GB, loads in
   5.6s and transcribes in **1.7–2.0s vs 2.5–2.9s for `small`/cpu** — faster *and* a
   far stronger model. Gate lowered to 2000; the app now runs turbo on GPU.
4. **Cold Bulgarian cleanup timed out.** Warm cleanup is 3.4s (EN) / 5.2s (BG), but the
   first call after a model load costs 12–22s against a 20s timeout — another silent
   raw-paste path. Timeout raised to 45s.

**Consequence:** the user's verdict "both languages are wrong" was formed over ~9
dictations running the weakest model (`small`) on CPU with **no AI cleanup at all**. That
configuration no longer exists.

## Core flow (v2 — unchanged from v1.5)

1. Tray app idles, models warm.
2. User holds the push-to-talk key.
3. Overlay shows recording/processing status, as today.
4. Release → full-audio transcription (turbo/cuda) → whole-utterance LLM cleanup.
5. Cleaned text → clipboard → Ctrl+V → clipboard restored.
6. Saved to SQLite history (raw + cleaned + app + status), as today.

## ASSUMPTIONS (no firm answer given — defaults chosen)

1. Max dictation length stays 120s (`max_record_s`).
2. EN/BG stay layout-selected; no detection work in v2.
3. Exact library versions to be confirmed against current docs at implementation time
   (standing project rule — no version guessing).

## OPEN RISKS

1. ~~**Bulgarian self-corrections are silently wrong.**~~ **RESOLVED 2026-07-22 — and
   the original diagnosis in this document was wrong.** Systematic investigation showed
   the failing test sentence ("…във вторник не чакай в сряда") was itself flawed: unlike
   English "no wait", Bulgarian "не чакай" is *also* a literal imperative ("do not
   wait"), so keeping "вторник" was a defensible reading. Every unambiguous BG
   self-correction marker (не, / извинявай / тоест / не, чакай,) already worked 3/3.

   The investigation did uncover a **worse, unrelated defect**: `FEW_SHOT["bg"]` used
   that same ambiguous "не чакай" as its self-correction example, which taught the model
   to treat "не чакай X" as *delete what follows*. Ordinary sentences lost content
   deterministically — "тръгвай веднага не чакай автобуса" → "Тръгвай веднага." (0/3
   kept the clause). Fixed by switching the example to the unambiguous "извинявай";
   the same sentences now survive 3/3. Regression test: `tests/check_cleanup_bg.py`.

   Remaining known limitation: a genuinely ambiguous "не чакай" with no punctuation is
   still read as an imperative. This is arguably correct and is deliberately not
   "fixed" — forcing the self-correction reading would delete real instructions.

2. **The Ollama tray app will re-break the models path.** *(Open — this is PLAN-v2 M4.)*
   The user's Startup shortcut launches `ollama app.exe` at login, which forces the bad
   `OLLAMA_MODELS`. FlowLocal now repairs this when *it* starts the server, but if the
   tray app wins the race and claims port 11434 first, cleanup is dead again until
   restart. The bad value's origin was never located — not in User/Machine env, registry,
   or `~/.ollama/config.json`.

3. **VRAM is shared and volatile.** turbo/cuda depends on ~2GB staying free; another app
   can take it mid-session. The existing CPU fallback covers correctness but produces a
   large, invisible latency cliff.

4. **This machine's free disk drops sharply under heavy model use, via the pagefile.**
   Observed 2026-07-23: holding several whisper models resident at once expanded the
   Windows pagefile to ~21GB, leaving 0.22GB free, at which point whisper could not
   allocate at all and FlowLocal refused to start (`mkl_malloc: failed to allocate
   memory`). Not a v2 code risk, but a standing operational constraint — check free disk
   before loading extra models for any future experiment, and don't hold more than the
   production set (turbo + the two Ollama models) resident at once.

5. **PySide6 licensing (LGPL/commercial) is unresolved for v3.** Irrelevant to v2, but
   it constrains a closed-source paid product and should be verified against Qt's
   current terms before v3 work starts, not after.

## Verification (how we'll know v2 works)

- Self-correction phrases produce the corrected version **in both languages** (M3, done).
- Kill Ollama mid-session → raw text pasted with a warning, nothing lost.
- Start with Ollama's tray app already running → app reports the real state instead
  of claiming health (regression test for the bug found on 2026-07-22; covered by M4).
