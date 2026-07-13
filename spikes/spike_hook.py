"""Spike: prove we can fully hijack CapsLock with a low-level keyboard hook.

Hold CapsLock  -> prints "HOLD x.xxs" on release (toggle suppressed, LED never changes)
Tap  (<0.3s)   -> prints "TAP ignored"
Other keys     -> pass through untouched
Ctrl+C in this console exits.
"""
import ctypes
import ctypes.wintypes as wt
import time

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WH_KEYBOARD_LL = 13
VK_CAPITAL = 0x14
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
LLKHF_INJECTED = 0x10

TAP_THRESHOLD_S = 0.3

LRESULT = ctypes.c_ssize_t


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wt.DWORD),
        ("scanCode", wt.DWORD),
        ("flags", wt.DWORD),
        ("time", wt.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wt.ULONG)),
    ]


HOOKPROC = ctypes.CFUNCTYPE(LRESULT, ctypes.c_int, wt.WPARAM, wt.LPARAM)

user32.SetWindowsHookExW.restype = wt.HHOOK
user32.SetWindowsHookExW.argtypes = (ctypes.c_int, HOOKPROC, wt.HINSTANCE, wt.DWORD)
user32.CallNextHookEx.restype = LRESULT
user32.CallNextHookEx.argtypes = (wt.HHOOK, ctypes.c_int, wt.WPARAM, wt.LPARAM)

_caps_is_down = False
_caps_down_at = 0.0


def _hook_proc(n_code, w_param, l_param):
    global _caps_is_down, _caps_down_at
    if n_code >= 0:
        kb = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
        if kb.vkCode == VK_CAPITAL and not (kb.flags & LLKHF_INJECTED):
            if w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
                if not _caps_is_down:  # dedupe auto-repeat
                    _caps_is_down = True
                    _caps_down_at = time.monotonic()
                    print("DOWN", flush=True)
                return 1  # suppress: LED/toggle never fires
            if w_param in (WM_KEYUP, WM_SYSKEYUP):
                if _caps_is_down:
                    _caps_is_down = False
                    held = time.monotonic() - _caps_down_at
                    if held < TAP_THRESHOLD_S:
                        print(f"TAP ignored ({held:.2f}s)", flush=True)
                    else:
                        print(f"HOLD {held:.2f}s", flush=True)
                return 1
    return user32.CallNextHookEx(None, n_code, w_param, l_param)


# module-level reference so the ctypes callback is never garbage-collected
_proc = HOOKPROC(_hook_proc)


def main():
    hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, _proc, None, 0)
    if not hook:
        raise ctypes.WinError(ctypes.get_last_error())
    print("Hook installed. Hold/tap CapsLock anywhere. Ctrl+C here to exit.", flush=True)
    msg = wt.MSG()
    try:
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
    except KeyboardInterrupt:
        pass
    finally:
        user32.UnhookWindowsHookEx(hook)
        print("Hook removed.", flush=True)


if __name__ == "__main__":
    main()
