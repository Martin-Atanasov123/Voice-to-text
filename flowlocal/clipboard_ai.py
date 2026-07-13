"""Clipboard AI: actions offered in the popup after the user copies text.

Summarize / Explain / Fix grammar reuse the rewrite transform machinery
(same-language, never-answer). Translate has its own system prompt because
it deliberately CHANGES the language (EN <-> BG).
"""
from .rewrite import STYLES, detect_language

MIN_CHARS = 30      # shorter copies are addresses/passwords/ids — don't offer AI
MAX_CHARS = 8000    # longer would blow the local models' context on CPU

ACTIONS: dict[str, tuple[str, str]] = {
    "summarize": (
        "Summarize",
        "Replace the text with a concise summary of 2-3 sentences that captures its key "
        "points and any decisions or numbers.",
    ),
    "translate": ("Translate BG⇄EN", ""),  # handled specially below
    "explain": (
        "Explain",
        "Replace the text with a short, simple explanation of what it means or does, "
        "understandable to a non-expert. A few sentences at most.",
    ),
    "grammar": ("Fix grammar", STYLES["grammar"][1]),
}

TRANSLATE_SYSTEM = (
    "You are a translation engine. Translate the user's text to {target}. Preserve meaning, "
    "tone, formatting and names; keep technical terms natural for the target language — "
    "widely used IT anglicisms may stay in English when that is how {target} speakers write. "
    "Translate every word faithfully; never substitute, add or drop information. "
    "Output ONLY the translation — no quotes, no explanations."
)

# Anchors faithful, natural translation in each direction.
_TRANSLATE_FEW_SHOT = {
    "bg": [  # target bg (input was en)
        {"role": "user", "content": "The release is planned for Friday morning."},
        {"role": "assistant", "content": "Релийзът е планиран за петък сутринта."},
    ],
    "en": [  # target en (input was bg)
        {"role": "user", "content": "Утре ще прегледам документа и ще ти пиша."},
        {"role": "assistant", "content": "I'll review the document tomorrow and write to you."},
    ],
}

_TARGET = {"en": ("Bulgarian", "bg"), "bg": ("English", "en")}

CLIPBOARD_TIMEOUT_S = 90.0  # copied text can be long; CPU prompt processing is slow


def run_action(cleaner, action: str, text: str) -> tuple[str, bool]:
    """Execute a clipboard action. Returns (result, ok)."""
    lang = detect_language(text)
    if action == "translate":
        target_name, target_code = _TARGET.get(lang, _TARGET["en"])
        messages = [
            {"role": "system", "content": TRANSLATE_SYSTEM.format(target=target_name)},
            *_TRANSLATE_FEW_SHOT[target_code],
            {"role": "user", "content": text},
        ]
        try:
            # model choice follows the TARGET language (BG model translates to BG best)
            out = cleaner._send(messages, target_code, timeout=CLIPBOARD_TIMEOUT_S)
            return (out, True) if out else (text, False)
        except Exception:
            return text, False
    label, instruction = ACTIONS[action]
    return cleaner.transform(text, instruction, lang, timeout=CLIPBOARD_TIMEOUT_S)
