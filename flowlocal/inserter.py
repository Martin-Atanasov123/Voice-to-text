"""Insert text into the focused app: save clipboard -> set text -> Ctrl+V -> restore.

Known v1 limitation: only plain-text clipboard content is saved/restored;
images/files on the clipboard are lost when a dictation pastes.
"""
import ctypes
import time

import win32clipboard
import win32con

user32 = ctypes.windll.user32

# While > monotonic(), clipboard changes are OURS — the Clipboard AI popup must
# not react to pastes/captures/restores this module performs.
suppress_until: float = 0.0


def _suppress(seconds: float = 2.0) -> None:
    global suppress_until
    suppress_until = time.monotonic() + seconds


VK_SHIFT, VK_CONTROL, VK_MENU, VK_LWIN, VK_RWIN = 0x10, 0x11, 0x12, 0x5B, 0x5C
KEYEVENTF_KEYUP = 0x0002
INPUT_KEYBOARD = 1


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("padding", ctypes.c_byte * 32)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("union", _INPUTUNION)]


def _send_key(vk: int, up: bool = False) -> None:
    inp = INPUT(type=INPUT_KEYBOARD)
    inp.union.ki = KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP if up else 0, 0, None)
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def _wait_modifiers_released(timeout_s: float = 1.0) -> None:
    """Injected Ctrl+V must not become Ctrl+Shift+V etc. while user's hands lift off."""
    deadline = time.monotonic() + timeout_s
    mods = (VK_SHIFT, VK_CONTROL, VK_MENU, VK_LWIN, VK_RWIN)
    while time.monotonic() < deadline:
        if not any(user32.GetAsyncKeyState(vk) & 0x8000 for vk in mods):
            return
        time.sleep(0.02)


def _open_clipboard_retry(attempts: int = 10, delay_s: float = 0.05) -> bool:
    for _ in range(attempts):
        try:
            win32clipboard.OpenClipboard()
            return True
        except Exception:
            time.sleep(delay_s)
    return False


def _get_clipboard_text() -> str | None:
    if not _open_clipboard_retry():
        return None
    try:
        if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
            return win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
        return None
    finally:
        win32clipboard.CloseClipboard()


def _set_clipboard_text(text: str) -> bool:
    _suppress()
    if not _open_clipboard_retry():
        return False
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
        return True
    finally:
        win32clipboard.CloseClipboard()


def capture_selection() -> tuple[str | None, str | None]:
    """Copy the current selection via Ctrl+C.

    Returns (selected_text, saved_clipboard). selected_text is None when nothing
    was selected (the clipboard stayed on our empty sentinel). The caller is
    responsible for eventually restoring saved_clipboard.
    """
    _wait_modifiers_released()
    _suppress(3.0)  # the Ctrl+C below is ours, not a user copy
    saved = _get_clipboard_text()
    _set_clipboard_text("")  # sentinel: unchanged means no selection
    _send_key(VK_CONTROL)
    _send_key(ord("C"))
    _send_key(ord("C"), up=True)
    _send_key(VK_CONTROL, up=True)
    time.sleep(0.15)
    text = _get_clipboard_text()
    return (text if text else None), saved


def restore_clipboard(saved: str | None) -> None:
    if saved is not None:
        _set_clipboard_text(saved)


def paste_replacing_selection(text: str, saved: str | None, restore_delay_s: float = 0.3) -> None:
    """Paste `text` over the current selection, then restore the saved clipboard."""
    if not text:
        return
    _wait_modifiers_released()
    if not _set_clipboard_text(text):
        raise RuntimeError("Could not open clipboard to set text")
    _send_key(VK_CONTROL)
    _send_key(ord("V"))
    _send_key(ord("V"), up=True)
    _send_key(VK_CONTROL, up=True)
    time.sleep(restore_delay_s)
    restore_clipboard(saved)


def insert_text(text: str, restore_delay_s: float = 0.3) -> None:
    """Paste `text` into the focused window via clipboard, restoring old text after."""
    if not text:
        return
    _wait_modifiers_released()
    saved = _get_clipboard_text()
    if not _set_clipboard_text(text):
        raise RuntimeError("Could not open clipboard to set text")
    _send_key(VK_CONTROL)
    _send_key(ord("V"))
    _send_key(ord("V"), up=True)
    _send_key(VK_CONTROL, up=True)
    time.sleep(restore_delay_s)  # let the target app read the clipboard first
    if saved is not None:
        _set_clipboard_text(saved)
