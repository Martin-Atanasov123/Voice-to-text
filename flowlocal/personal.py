"""Personal dictionary and voice snippets (Wispr Flow-style).

- Dictionary: names/terms that must always be spelled correctly. Fed to
  Whisper as hotwords and to the cleanup prompt as a spelling contract.
- Snippets: short spoken cue -> full stored text pasted verbatim (no cleanup).

Both live as JSON in %APPDATA%\\FlowLocal.
"""
import json
import re
import unicodedata

from .config import APP_DIR

DICT_PATH = APP_DIR / "dictionary.json"
SNIPPETS_PATH = APP_DIR / "snippets.json"


def _load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _save(path, data) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


class Dictionary:
    """Ordered list of unique terms (case preserved, e.g. 'Supabase', 'Атанасов')."""

    def __init__(self):
        self.terms: list[str] = _load(DICT_PATH, [])

    def add(self, term: str) -> None:
        term = term.strip()
        if term and term.lower() not in (t.lower() for t in self.terms):
            self.terms.append(term)
            _save(DICT_PATH, self.terms)

    def remove(self, term: str) -> None:
        self.terms = [t for t in self.terms if t.lower() != term.lower()]
        _save(DICT_PATH, self.terms)

    def hotwords(self) -> str | None:
        """Whisper 'hotwords' string biasing recognition toward these terms."""
        return ", ".join(self.terms) if self.terms else None

    def prompt_clause(self, language: str) -> str:
        """Extra system-prompt rule enforcing exact spellings during cleanup."""
        if not self.terms:
            return ""
        listed = ", ".join(self.terms)
        if language == "bg":
            return (
                "\n\nЛИЧЕН РЕЧНИК: следните имена/термини се изписват ТОЧНО така, "
                f"когато се срещат (поправяй сгрешени варианти към тях): {listed}"
            )
        return (
            "\n\nPERSONAL DICTIONARY: the following names/terms must be spelled EXACTLY "
            f"like this whenever they occur (correct misheard variants to them): {listed}"
        )


def _normalize(text: str) -> str:
    """Lowercase, strip punctuation/extra spaces — tolerant cue matching."""
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"[^\w\s]", "", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


class Snippets:
    """{spoken cue -> expansion text}. Cue match is on the whole normalized utterance."""

    def __init__(self):
        self.items: dict[str, str] = _load(SNIPPETS_PATH, {})

    def set(self, cue: str, text: str) -> None:
        cue = cue.strip()
        if cue and text:
            self.items[cue] = text
            _save(SNIPPETS_PATH, self.items)

    def remove(self, cue: str) -> None:
        self.items.pop(cue, None)
        _save(SNIPPETS_PATH, self.items)

    def match(self, transcript: str) -> str | None:
        """Expansion text if the transcript is exactly one of the cues (fuzzy on
        case/punctuation), else None."""
        norm = _normalize(transcript)
        if not norm:
            return None
        for cue, text in self.items.items():
            if _normalize(cue) == norm:
                return text
        return None
