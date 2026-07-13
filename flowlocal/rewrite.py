"""Rewrite-on-demand styles: select text anywhere -> Ctrl+CapsLock -> pick one.

Each style is (button label, LLM instruction). The instruction is embedded in
cleanup.REWRITE_SYSTEM which already enforces same-language, no-answering output.
"""

STYLES: dict[str, tuple[str, str]] = {
    "professional": (
        "Professional",
        "Rewrite the text in a professional, polished business tone. Clear, courteous, "
        "no slang, well-structured sentences.",
    ),
    "friendly": (
        "Friendly",
        "Rewrite the text in a warm, friendly, conversational tone. Relaxed but respectful; "
        "contractions are fine.",
    ),
    "shorter": (
        "Shorter",
        "Condense the text to roughly half its length. Keep every essential fact; cut "
        "repetition, hedging and filler.",
    ),
    "longer": (
        "Longer",
        "Expand the text with a bit more detail and smoother connective flow. Do not invent "
        "new facts — elaborate only on what is already stated.",
    ),
    "email": (
        "Email",
        "Reformat the text as a complete, polite email: greeting line, short well-spaced "
        "paragraphs, closing line. Invent no names — use a generic greeting if none is given.",
    ),
    "grammar": (
        "Fix grammar",
        "Correct all spelling, grammar and punctuation mistakes. Change NOTHING else — keep "
        "wording, tone and formatting as close to the original as possible.",
    ),
}


def detect_language(text: str) -> str:
    """'bg' if the text is predominantly Cyrillic, else 'en' (picks cleanup model)."""
    cyr = sum(1 for ch in text if "Ѐ" <= ch <= "ӿ")
    letters = sum(1 for ch in text if ch.isalpha())
    return "bg" if letters and cyr / letters > 0.4 else "en"
