"""Pick dictation language from the focused window's keyboard layout."""
import ctypes

user32 = ctypes.windll.user32

LANG_MAP = {0x0409: "en", 0x0402: "bg"}


def get_dictation_language() -> str:
    hwnd = user32.GetForegroundWindow()
    tid = user32.GetWindowThreadProcessId(hwnd, None)
    hkl = user32.GetKeyboardLayout(tid)
    return LANG_MAP.get(hkl & 0xFFFF, "en")
