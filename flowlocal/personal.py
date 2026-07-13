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


PROFILES = {
    "general": {"en": "", "bg": ""},
    "developer": {
        "en": "\n\nPROFILE: the user is a software developer. Treat words like commit, deploy, "
              "merge, endpoint, prop, hook as technical vocabulary — never 'correct' them; "
              "keep code identifiers and product names verbatim.",
        "bg": "\n\nПРОФИЛ: потребителят е програмист. Думи като commit, deploy, merge, "
              "endpoint са технически термини — никога не ги 'поправяй' и не ги превеждай; "
              "запазвай идентификатори и имена на продукти дословно.",
    },
    "student": {
        "en": "\n\nPROFILE: the user is a student. Lean toward clear, well-structured prose "
              "suitable for coursework and notes.",
        "bg": "\n\nПРОФИЛ: потребителят е студент. Предпочитай ясна, добре структурирана реч, "
              "подходяща за учебни материали и записки.",
    },
}


def profile_clause(profile: str, language: str) -> str:
    entry = PROFILES.get(profile, PROFILES["general"])
    return entry.get(language, entry["en"])


def style_clause(sample: str, language: str) -> str:
    sample = sample.strip()[:500]
    if not sample:
        return ""
    if language == "bg":
        return (
            "\n\nСТИЛ НА ПОТРЕБИТЕЛЯ: когато избираш измежду равностойни формулировки, "
            f"следвай тона и навиците от този негов примерен текст:\n---\n{sample}\n---"
        )
    return (
        "\n\nUSER'S STYLE: when choosing between equivalent phrasings, match the tone and "
        f"habits of this sample of their writing:\n---\n{sample}\n---"
    )


_BG_DAYS = ["понеделник", "вторник", "сряда", "четвъртък", "петък", "събота", "неделя"]
_EN_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def render_snippet(text: str) -> str:
    """Fill {{date}}, {{time}}, {{day}} placeholders at paste time."""
    if "{{" not in text:
        return text
    import datetime

    now = datetime.datetime.now()
    has_cyrillic = any("Ѐ" <= ch <= "ӿ" for ch in text)
    day = (_BG_DAYS if has_cyrillic else _EN_DAYS)[now.weekday()]
    return (
        text.replace("{{date}}", now.strftime("%d.%m.%Y"))
        .replace("{{time}}", now.strftime("%H:%M"))
        .replace("{{day}}", day)
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
