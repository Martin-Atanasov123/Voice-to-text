"""Transcript cleanup via local Ollama chat API.

clean() returns (text, ok). ok=False means the caller should paste the RAW
transcript — the user's words are never lost because cleanup failed.
"""
import json
import logging
import urllib.error
import urllib.request

log = logging.getLogger(__name__)

PROMPTS = {
    "en": (
        "You clean up voice-dictation transcripts. Rules:\n"
        "- Remove filler words (um, uh, like, you know) and false starts.\n"
        "- When the speaker corrects themselves, ALWAYS keep the LAST stated value:\n"
        "  'Tuesday... no wait, Wednesday' -> 'Wednesday'; 'two pizzas, no, three pizzas' -> 'three pizzas'.\n"
        "- Fix grammar, punctuation and capitalization.\n"
        "- Keep the speaker's meaning, wording and tone. Do not add or invent anything.\n"
        "- Reply in English, with ONLY the cleaned text. No quotes, no explanations."
    ),
    "bg": (
        "Ти изчистваш транскрипции от гласова диктовка на български. Правила:\n"
        "- Премахвай паразитни думи (ами, ъъъ, значи, такова) и фалстартове.\n"
        "- При самокорекция ВИНАГИ запазвай ПОСЛЕДНАТА казана стойност:\n"
        "  'във вторник... не, чакай, в сряда' става 'в сряда'; 'две пици, не, три пици' става 'три пици'.\n"
        "- Поправяй граматика, пунктуация и главни букви.\n"
        "- Запазвай смисъла, думите и тона на говорещия. Не добавяй нищо ново.\n"
        "- Отговаряй на български, САМО с изчистения текст. Без кавички, без обяснения."
    ),
}


class OllamaCleaner:
    """models: per-language map, e.g. {"en": "qwen2.5:3b-instruct", "bg": "qwen3:4b-..."}."""

    def __init__(self, url: str, models: dict[str, str] | str, timeout_s: float = 20.0):
        self.base = url.rstrip("/")
        self.models = {"en": models, "bg": models} if isinstance(models, str) else models
        self.timeout_s = timeout_s

    def _post(self, path: str, payload: dict, timeout: float) -> dict:
        req = urllib.request.Request(
            self.base + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def health_check(self) -> bool:
        try:
            with urllib.request.urlopen(self.base + "/api/version", timeout=2) as resp:
                resp.read()
            return True
        except (urllib.error.URLError, OSError):
            return False

    def warm_up(self) -> None:
        """Load the models into memory so the first real cleanup isn't 5-15s slower."""
        for lang in dict.fromkeys(self.models):  # unique langs, keep order
            try:
                self._chat("Hello", lang, timeout=120)
            except Exception as e:
                log.warning("Ollama warm-up (%s) failed: %s", lang, e)

    def _chat(self, text: str, language: str, timeout: float) -> str:
        data = self._post(
            "/api/chat",
            {
                "model": self.models.get(language, self.models["en"]),
                "messages": [
                    {"role": "system", "content": PROMPTS.get(language, PROMPTS["en"])},
                    {"role": "user", "content": text},
                ],
                "stream": False,
                "keep_alive": "30m",
                # num_gpu=0: whisper owns the 4GB GPU; the 3B LLM runs on CPU
                "options": {"temperature": 0.2, "num_gpu": 0},
            },
            timeout=timeout,
        )
        return data["message"]["content"].strip()

    def clean(self, raw: str, language: str) -> tuple[str, bool]:
        try:
            cleaned = self._chat(raw, language, timeout=self.timeout_s)
            # Guard against a chatty/broken model reply: if the output is empty or
            # wildly longer than the input, the raw transcript is safer.
            if not cleaned or len(cleaned) > max(200, len(raw) * 3):
                log.warning("Cleanup output rejected (len raw=%d cleaned=%d)", len(raw), len(cleaned))
                return raw, False
            return cleaned, True
        except Exception as e:
            log.warning("Cleanup failed: %s", e)
            return raw, False
