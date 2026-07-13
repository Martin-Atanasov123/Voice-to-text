"""Smart Context: the focused app decides the dictation's tone.

Foreground exe -> tone category -> extra clause appended to the cleanup prompt.
No modes to pick — Discord gets casual, Outlook gets email prose, IDEs keep
technical wording, automatically.
"""
import ctypes
import ctypes.wintypes
from pathlib import Path

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def foreground_exe() -> str:
    """Lower-case exe name of the focused window ('discord.exe'), '?' if unknown."""
    try:
        hwnd = user32.GetForegroundWindow()
        pid = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not handle:
            return "?"
        try:
            buf = ctypes.create_unicode_buffer(1024)
            size = ctypes.wintypes.DWORD(1024)
            if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                return Path(buf.value).name.lower()
            return "?"
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return "?"


APP_TONE: dict[str, str] = {
    # chat — casual
    "discord.exe": "casual", "slack.exe": "casual", "telegram.exe": "casual",
    "whatsapp.exe": "casual", "viber.exe": "casual", "messenger.exe": "casual",
    "signal.exe": "casual",
    # email — structured, polite
    "outlook.exe": "email", "olk.exe": "email", "thunderbird.exe": "email",
    "hxoutlook.exe": "email",
    # code — keep technical wording intact
    "code.exe": "code", "cursor.exe": "code", "devenv.exe": "code",
    "windowsterminal.exe": "code", "wt.exe": "code", "pycharm64.exe": "code",
    "idea64.exe": "code", "sublime_text.exe": "code", "notepad++.exe": "code",
    # documents — polished prose
    "winword.exe": "formal", "powerpnt.exe": "formal", "acrobat.exe": "formal",
}

TONE_CLAUSES = {
    "casual": {
        "en": "\n\nCONTEXT: the user is dictating into a chat app. Keep the result relaxed "
              "and conversational — contractions and informal phrasing are welcome; do not "
              "formalize the tone.",
        "bg": "\n\nКОНТЕКСТ: потребителят диктува в чат приложение. Запази текста разговорен "
              "и непринуден — не го прави официален.",
    },
    "email": {
        "en": "\n\nCONTEXT: the user is dictating an email. Prefer complete, polite sentences "
              "and clean paragraph breaks suitable for correspondence.",
        "bg": "\n\nКОНТЕКСТ: потребителят диктува имейл. Предпочитай завършени, учтиви "
              "изречения и ясни абзаци, подходящи за кореспонденция.",
    },
    "code": {
        "en": "\n\nCONTEXT: the user is dictating into a code editor or terminal. Keep "
              "technical terms, identifiers and file names exactly as spoken; do not add "
              "decorative punctuation; keep it terse.",
        "bg": "\n\nКОНТЕКСТ: потребителят диктува в редактор за код или терминал. Запазвай "
              "технически термини, идентификатори и имена на файлове точно както са казани; "
              "без излишна пунктуация; кратко.",
    },
    "formal": {
        "en": "\n\nCONTEXT: the user is dictating into a document. Aim for polished, "
              "well-structured written prose.",
        "bg": "\n\nКОНТЕКСТ: потребителят диктува в документ. Стреми се към изгладена, "
              "добре структурирана писмена реч.",
    },
}


def tone_clause(exe_name: str, language: str) -> str:
    """Extra cleanup-prompt clause for this app, or '' when no mapping applies."""
    tone = APP_TONE.get(exe_name.lower())
    if tone is None:
        return ""
    return TONE_CLAUSES[tone].get(language, TONE_CLAUSES[tone]["en"])
