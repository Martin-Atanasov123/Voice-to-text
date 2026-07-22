"""Regression check for Bulgarian cleanup: self-corrections and imperatives.

Run:  .venv\\Scripts\\python tests\\check_cleanup_bg.py

Why this exists
---------------
Bulgarian "не чакай" is ambiguous in a way the English "no wait" is not: it is
both a self-correction discourse marker AND a literal imperative ("do not
wait"). A few-shot example that used the ambiguous form taught the model to
treat "не чакай X" as a signal to DELETE content, so a perfectly ordinary
sentence like "тръгвай веднага не чакай автобуса" came back as "Тръгвай
веднага." — the instruction silently vanished, 3 times out of 3.

The self-correction cases below use unambiguous markers, which is what real
dictation produces once Whisper inserts punctuation. The IMPERATIVE case is the
important one: it must never be treated as a self-correction.

Needs Ollama running with the configured BG model; skips (exit 0) if unavailable.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flowlocal.config import Config
from flowlocal.cleanup import create_cleaner

# (label, input, must_appear, must_not_appear or None)
CASES = [
    ("self-correction: не,",
     "мисля че трябва да се видим във вторник... не, в сряда", "сряда", "вторник"),
    ("self-correction: извинявай",
     "мисля че трябва да се видим във вторник, извинявай, в сряда", "сряда", "вторник"),
    ("self-correction: тоест",
     "мисля че трябва да се видим във вторник, тоест в сряда", "сряда", "вторник"),
    ("self-correction: не, чакай,",
     "мисля че трябва да се видим във вторник не, чакай, в сряда", "сряда", "вторник"),
    ("IMPERATIVE must survive",
     "тръгвай веднага не чакай автобуса", "не чакай", None),
    ("IMPERATIVE must survive (2)",
     "звънни ми утре не чакай да ти пиша", "не чакай", None),
]


def main() -> int:
    cfg = Config.load()
    cleaner = create_cleaner(cfg)
    if not cleaner.health_check():
        print("SKIP: cleanup backend unavailable (Ollama down or models missing)")
        return 0

    failures = 0
    for label, text, must_appear, must_not in CASES:
        out, ok = cleaner.clean(text, "bg")
        low = out.lower()
        good = ok and must_appear.lower() in low and (must_not is None or must_not not in low)
        print(f"[{'PASS' if good else 'FAIL'}] {label}\n       {out}")
        if not good:
            want = f"expected '{must_appear}'"
            if must_not:
                want += f" and NOT '{must_not}'"
            print(f"       {want}")
            failures += 1

    print(f"\n{len(CASES) - failures}/{len(CASES)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
