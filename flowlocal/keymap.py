"""Friendly names for Windows virtual-key codes, and a curated set of good
push-to-talk key choices.

A key is identified as (vk, extended) because Windows' low-level keyboard
hook reports Left/Right Ctrl and Left/Right Alt with the SAME generic vkCode
(VK_CONTROL / VK_MENU) — only the LLKHF_EXTENDED flag on the key event tells
them apart. Shift is the odd one out: Windows already reports distinct
VK_LSHIFT/VK_RSHIFT codes, so `extended` is irrelevant there (kept False).
"""
import ctypes

user32 = ctypes.windll.user32

VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12  # Alt
VK_CAPITAL = 0x14
VK_ESCAPE = 0x1B
VK_LSHIFT = 0xA0
VK_RSHIFT = 0xA1
VK_LWIN = 0x5B
VK_RWIN = 0x5C
VK_SCROLL = 0x91
VK_PAUSE = 0x13

user32.MapVirtualKeyW.restype = ctypes.c_uint
user32.MapVirtualKeyW.argtypes = (ctypes.c_uint, ctypes.c_uint)
user32.GetKeyNameTextW.restype = ctypes.c_int
user32.GetKeyNameTextW.argtypes = (ctypes.c_long, ctypes.c_wchar_p, ctypes.c_int)

MAPVK_VK_TO_VSC = 0
EXTENDED_BIT = 1 << 24


# MapVirtualKey has no scan-code entry for these — Windows/Pause predate (or sit
# outside) the legacy 101-key scan-code table it's built from.
_NAME_OVERRIDES = {
    (VK_LWIN, False): "Left Windows",
    (VK_RWIN, False): "Right Windows",
    (VK_PAUSE, False): "Pause / Break",
}


def key_name(vk: int, extended: bool) -> str:
    """Windows' own display name for a (vk, extended) key, e.g. 'Right Ctrl'."""
    if (vk, extended) in _NAME_OVERRIDES:
        return _NAME_OVERRIDES[(vk, extended)]
    scan = user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC)
    if not scan:
        return f"Key 0x{vk:02X}"
    lparam = (scan << 16) | (EXTENDED_BIT if extended else 0)
    buf = ctypes.create_unicode_buffer(64)
    n = user32.GetKeyNameTextW(lparam, buf, 64)
    return buf.value if n else f"Key 0x{vk:02X}"


# Curated, safe push-to-talk candidates. Left Ctrl/Alt/Win are deliberately
# excluded — they collide with far too many normal shortcuts.
RECOMMENDED_PTT_KEYS: list[tuple[int, bool]] = [
    (VK_CAPITAL, False),
    (VK_CONTROL, True),   # Right Ctrl
    (VK_MENU, True),      # Right Alt
    (VK_RSHIFT, False),
    (VK_RWIN, False),
    (VK_SCROLL, False),
    (VK_PAUSE, False),
]

DEFAULT_PTT = (VK_CAPITAL, False)

MODIFIER_CHOICES: list[tuple[str, str]] = [
    ("ctrl", "Ctrl"),
    ("shift", "Shift"),
    ("alt", "Alt"),
]

MODIFIER_VK: dict[str, int] = {"ctrl": VK_CONTROL, "shift": VK_SHIFT, "alt": VK_MENU}

DEFAULT_REWRITE_MODIFIER = "ctrl"
DEFAULT_COMMAND_MODIFIER = "shift"


def key_family(vk: int) -> str | None:
    """Which modifier family a captured vk belongs to, or None (not a modifier)."""
    if vk == VK_CONTROL:
        return "ctrl"
    if vk == VK_MENU:
        return "alt"
    if vk in (VK_SHIFT, VK_LSHIFT, VK_RSHIFT):
        return "shift"
    if vk in (VK_LWIN, VK_RWIN):
        return "win"
    return None
