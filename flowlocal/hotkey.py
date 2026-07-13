"""CapsLock push-to-talk via a low-level Windows keyboard hook.

Runs the hook + message pump on its own thread. CapsLock is fully hijacked:
its toggle never fires. Hold >= tap_threshold -> on_press at key-down and
on_release(held_seconds) at key-up; shorter taps -> on_tap().

Hook-proc rules (Windows removes hooks that exceed ~300ms):
- no allocation-heavy work, no logging, no Qt calls
- callbacks must return fast; heavy work belongs on other threads
- module/instance-level reference to HOOKPROC prevents GC crash
"""
import ctypes
import ctypes.wintypes as wt
import threading
import time
from typing import Callable

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WH_KEYBOARD_LL = 13
VK_CAPITAL = 0x14
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_QUIT = 0x0012
LLKHF_INJECTED = 0x10

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


class CapsLockHook(threading.Thread):
    """on_press() fires at key-down; on_release(held) or on_tap() at key-up."""

    def __init__(
        self,
        on_press: Callable[[], None],
        on_release: Callable[[float], None],
        on_tap: Callable[[], None] | None = None,
        tap_threshold_s: float = 0.3,
    ):
        super().__init__(name="capslock-hook", daemon=True)
        self.on_press = on_press
        self.on_release = on_release
        self.on_tap = on_tap or (lambda: None)
        self.tap_threshold_s = tap_threshold_s
        self.enabled = True  # when False, CapsLock passes through untouched
        self._is_down = False
        self._down_at = 0.0
        self._proc = HOOKPROC(self._hook_proc)  # keep ref: GC'd callback = crash
        self._hook = None
        self._tid: int | None = None
        self._ready = threading.Event()

    def _hook_proc(self, n_code, w_param, l_param):
        if n_code >= 0 and self.enabled:
            kb = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            if kb.vkCode == VK_CAPITAL and not (kb.flags & LLKHF_INJECTED):
                if w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
                    if not self._is_down:  # dedupe key auto-repeat
                        self._is_down = True
                        self._down_at = time.monotonic()
                        try:
                            self.on_press()
                        except Exception:
                            pass
                    return 1  # suppress toggle
                if w_param in (WM_KEYUP, WM_SYSKEYUP):
                    if self._is_down:
                        self._is_down = False
                        held = time.monotonic() - self._down_at
                        try:
                            if held < self.tap_threshold_s:
                                self.on_tap()
                            else:
                                self.on_release(held)
                        except Exception:
                            pass
                    return 1
        return user32.CallNextHookEx(None, n_code, w_param, l_param)

    def run(self):
        self._tid = kernel32.GetCurrentThreadId()
        self._hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, None, 0)
        self._ready.set()
        if not self._hook:
            return
        msg = wt.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        user32.UnhookWindowsHookEx(self._hook)
        self._hook = None

    def start(self):
        super().start()
        self._ready.wait(timeout=2.0)
        if not self._hook:
            raise OSError("Failed to install keyboard hook")

    def stop(self):
        if self._tid is not None:
            user32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0)
            self.join(timeout=2.0)
