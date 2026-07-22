# FlowLocal v2 — Spec

## Context

FlowLocal v1.5 works: dictation, rewrite-on-selection, Command Mode, Clipboard AI,
dictionary, snippets, profiles, configurable hotkeys. This spec covers v2, produced
through a structured interview on 2026-07-22.

The interview started from three stated complaints — **missing Wispr Flow features,
speed, and accuracy in both languages** — but diagnosis during the interview showed
that most of the accuracy complaint had a different cause than assumed. See
"What the diagnosis changed" below; it materially reduces v2's scope.

## Spec Summary

### Product & users
- Unchanged: single-user, Windows, fully local, tray app. Same core gesture.
- **v2 targets the owner's machine only.** Public release is explicitly **v3**.
- Long-term direction (decided, not built in v2): replace the Ollama dependency
  with **inference bundled into the app** (llama.cpp/GGUF), because no ordinary
  user will install Ollama and pull models by hand. v2 must therefore **not deepen
  the coupling to Ollama** — new cleanup work goes behind the existing
  `_BaseCleaner` interface in `cleanup.py`, which already abstracts backends via
  `create_cleaner(cfg)`.

### The one new feature: live preview while speaking
- While the push-to-talk key is held, partial transcription appears **inside
  FlowLocal's own overlay**, updating as the user speaks.
- **Nothing is inserted into the target app until release.** On release the full
  audio is transcribed and cleaned as it is today, and only that final polished
  text is pasted.
- Rationale: whole-utterance cleanup is what makes self-corrections work
  ("Tuesday… no wait, Wednesday" → "Wednesday"). Streaming text directly into the
  focused app would require retroactively rewriting already-inserted text via
  simulated backspaces — fragile, and impossible in some apps. Preview in our own
  window gives the live feel at zero cost to output quality.
- The streamed partials are **preview-only**; they never become the pasted text.

### Speed
- The hard "<1s after release" target was **withdrawn during the interview** in
  favour of quality: "не е задължително да е под 1 секунда, но определено трябва
  някаква оптимизация със скоростта."
- Target: measurable improvement over v1.5, with cleanup quality untouched.
- Largest win already banked (see below): GPU transcription.

### Accuracy
- Re-evaluated **after** the fixes below, then scoped. The user explicitly chose
  "fix, test, then decide" over planning the whole accuracy workstream up front.
- One accuracy defect is already confirmed and does **not** depend on re-measurement:
  the Bulgarian cleanup model mishandles self-corrections (see Risks).

### Out of scope for v2
- Direct streaming insertion into the target app.
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

**Consequence for planning:** the user's verdict "both languages are wrong" was formed
over ~9 dictations running the weakest model (`small`) on CPU with **no AI cleanup at
all**. That configuration no longer exists. The accuracy workstream must be re-scoped
against fresh evidence rather than against that verdict.

## Core flow (v2, changes marked ▲)

1. Tray app idles, models warm.
2. User holds the push-to-talk key.
3. Overlay appears. ▲ **Partial transcript streams into the overlay while speaking.**
4. Release → full-audio transcription (turbo/cuda) → whole-utterance LLM cleanup.
5. Cleaned text → clipboard → Ctrl+V → clipboard restored.
6. Saved to SQLite history (raw + cleaned + app + status), as today.

## ASSUMPTIONS (no firm answer given — defaults chosen)

1. Preview granularity is **segment/sentence level**, not word-by-word — it follows
   faster-whisper's natural segment boundaries rather than a custom decoder loop.
2. The final paste always comes from a **fresh full-audio pass**, never from stitched
   partials, since chunked transcription is less accurate across chunk boundaries.
3. Streaming runs on the **same single model instance**; no second model is loaded for
   partials (4GB VRAM cannot host two).
4. If streaming can't keep up in real time, the overlay silently falls behind and
   catches up — it never delays or degrades the final result.
5. Max dictation length stays 120s (`max_record_s`).
6. EN/BG stay layout-selected; no detection work in v2.
7. Exact library versions to be confirmed against current docs at implementation time
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
2. **The Ollama tray app will re-break the models path.** The user's Startup shortcut
   launches `ollama app.exe` at login, which forces the bad `OLLAMA_MODELS`. FlowLocal
   now repairs this when *it* starts the server, but if the tray app wins the race and
   claims port 11434 first, cleanup is dead again until restart. The bad value's origin
   was never located — not in User/Machine env, registry, or `~/.ollama/config.json`.
3. **Accuracy scope is unknown until re-measured.** v2 may need no accuracy work at all,
   or may need a different BG cleanup model. Do not commit engineering to this yet.
4. **VRAM is shared and volatile.** turbo/cuda depends on ~2GB staying free; another app
   can take it mid-session. The existing CPU fallback covers correctness but produces a
   large, invisible latency cliff.
5. **Streaming may contend with the final pass** for the same model instance, making
   release-to-paste *slower* than v1.5 — the opposite of the goal. Needs measurement
   before committing to the design.
6. **PySide6 licensing (LGPL/commercial) is unresolved for v3.** Irrelevant to v2, but
   it constrains a closed-source paid product and should be verified against Qt's
   current terms before v3 work starts, not after.

## Verification (how we'll know v2 works)

- Dictate EN and BG into Notepad, Chrome and Word: live text appears in the overlay
  while speaking; the pasted result is cleaned, and the clipboard is restored.
- Release-to-paste latency measured against a v1.5 baseline on identical audio.
- Self-correction phrases produce the corrected version **in both languages**.
- Kill Ollama mid-session → raw text pasted with a warning, nothing lost.
- Start with Ollama's tray app already running → app reports the real state instead
  of claiming health (regression test for the bug found today).
