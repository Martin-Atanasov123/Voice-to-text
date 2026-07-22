"""Configurable push-to-talk key via a low-level Windows keyboard hook.

Runs the hook + message pump on its own thread. The chosen primary key is
fully hijacked: its normal effect (CapsLock toggle, ScrollLock toggle, etc.)
never fires. Hold >= tap_threshold -> on_press at key-down and
on_release(held_seconds) at key-up; shorter taps -> on_tap(). Holding the
rewrite/command modifier at the moment the primary key goes down fires
on_combo()/on_press(command=True) instead of plain dictation.

The same hook doubles as a generic "press any key" capturer for the Hotkeys
settings UI (begin_capture) — necessary because once a key is hijacked here,
Qt never sees it, so there is no other reliable way to let the user pick it.

Hook-proc rules (Windows silently REMOVES a low-level hook whose proc doesn't
return within ~300ms — LowLevelHooksTimeout — leaving the app running but
completely unresponsive to the key, with no error and no way to recover short
of restarting. Observed in practice: heavy CPU-bound work elsewhere in the
process (e.g. faster-whisper transcription) can starve this thread of the GIL
long enough to trip that timeout):
- no allocation-heavy work in the hot path; callbacks must return fast
- module/instance-level reference to HOOKPROC prevents GC crash
- run() periodically re-registers the hook (see _REFRESH_MS) as a safety net:
  if Windows ever drops it silently, this recovers within one interval
  without the user needing to notice or restart anything
"""
import ctypes
import ctypes.wintypes as wt
import logging
import threading
import time
from typing import Callable

from .keymap import DEFAULT_PTT, MODIFIER_VK, VK_ESCAPE

log = logging.getLogger(__name__)

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_QUIT = 0x0012
WM_TIMER = 0x0113
_REFRESH_MS = 120_000  # 2 min: recovery window if Windows silently drops the hook
LLKHF_EXTENDED = 0x01
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
user32.SetTimer.restype = ctypes.c_size_t  # UINT_PTR
user32.SetTimer.argtypes = (wt.HWND, ctypes.c_size_t, ctypes.c_uint, ctypes.c_void_p)
user32.KillTimer.argtypes = (wt.HWND, ctypes.c_size_t)


class PTTHook(threading.Thread):
    """Gestures on the configured primary key:
    - hold primary                  -> on_press(command=False) … on_release(held)
    - hold command_modifier+primary -> on_press(command=True)  … on_release(held)
    - rewrite_modifier+primary      -> on_combo() (rewrite selection)
    - tap (<threshold)               -> on_tap()
    """

    def __init__(
        self,
        on_press: Callable[[bool], None],
        on_release: Callable[[float], None],
        on_tap: Callable[[], None] | None = None,
        tap_threshold_s: float = 0.3,
        on_combo: Callable[[], None] | None = None,
        primary_vk: int = DEFAULT_PTT[0],
        primary_extended: bool = DEFAULT_PTT[1],
        rewrite_modifier_vk: int = MODIFIER_VK["ctrl"],
        command_modifier_vk: int = MODIFIER_VK["shift"],
    ):
        super().__init__(name="ptt-hook", daemon=True)
        self.on_press = on_press
        self.on_release = on_release
        self.on_tap = on_tap or (lambda: None)
        self.on_combo = on_combo or (lambda: None)
        self.tap_threshold_s = tap_threshold_s
        self.primary_vk = primary_vk
        self.primary_extended = primary_extended
        self.rewrite_modifier_vk = rewrite_modifier_vk
        self.command_modifier_vk = command_modifier_vk
        self.enabled = True  # when False, the primary key passes through untouched
        self._is_down = False
        self._is_combo = False
        self._down_at = 0.0
        self._proc = HOOKPROC(self._hook_proc)  # keep ref: GC'd callback = crash
        self._hook = None
        self._tid: int | None = None
        self._ready = threading.Event()
        # "press any key" capture mode, used by the Hotkeys settings UI
        self._capture_cb: Callable[[int | None, bool], None] | None = None
        self._capture_vk: int | None = None

    def begin_capture(self, callback: Callable[[int | None, bool], None]) -> None:
        """Next physical key press is reported as callback(vk, extended);
        Escape reports callback(None, False) (cancelled). Swallows that one
        keystroke system-wide so it doesn't leak into whatever app is focused."""
        self._capture_vk = None
        self._capture_cb = callback

    def _hook_proc(self, n_code, w_param, l_param):
        if n_code >= 0 and self.enabled:
            kb = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            if kb.flags & LLKHF_INJECTED:
                return user32.CallNextHookEx(None, n_code, w_param, l_param)

            # _capture_vk stays set between the captured key's down and up even
            # after _capture_cb is cleared, so the matching key-up is still
            # caught below and suppressed (otherwise it would leak to the OS —
            # e.g. releasing ScrollLock would reach the foreground app).
            if self._capture_cb is not None or self._capture_vk is not None:
                if w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
                    if self._capture_vk is None:
                        self._capture_vk = kb.vkCode
                        cb, self._capture_cb = self._capture_cb, None
                        try:
                            if kb.vkCode == VK_ESCAPE:
                                cb(None, False)
                            else:
                                cb(kb.vkCode, bool(kb.flags & LLKHF_EXTENDED))
                        except Exception:
                            log.exception("key-capture callback failed")
                    return 1
                if w_param in (WM_KEYUP, WM_SYSKEYUP) and kb.vkCode == self._capture_vk:
                    self._capture_vk = None
                    return 1
                return user32.CallNextHookEx(None, n_code, w_param, l_param)

            extended = bool(kb.flags & LLKHF_EXTENDED)
            if kb.vkCode == self.primary_vk and extended == self.primary_extended:
                if w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
                    if not self._is_down:  # dedupe key auto-repeat
                        self._is_down = True
                        self._down_at = time.monotonic()
                        self._is_combo = bool(
                            user32.GetAsyncKeyState(self.rewrite_modifier_vk) & 0x8000
                        )
                        try:
                            if self._is_combo:
                                self.on_combo()
                            else:
                                command = bool(
                                    user32.GetAsyncKeyState(self.command_modifier_vk) & 0x8000
                                )
                                self.on_press(command)
                        except Exception:
                            log.exception("on_press/on_combo callback failed")
                    return 1  # suppress the key's normal effect
                if w_param in (WM_KEYUP, WM_SYSKEYUP):
                    if self._is_down:
                        self._is_down = False
                        held = time.monotonic() - self._down_at
                        try:
                            if self._is_combo:
                                self._is_combo = False  # combo fired on key-down
                            elif held < self.tap_threshold_s:
                                self.on_tap()
                            else:
                                self.on_release(held)
                        except Exception:
                            log.exception("on_tap/on_release callback failed")
                    return 1
        return user32.CallNextHookEx(None, n_code, w_param, l_param)

    def _reinstall_hook(self) -> None:
        """Re-register the hook. Installs the replacement before removing the
        old one so there is never a gap with zero hooks active; any physical
        key event landing in between is handled twice by the same stateful
        _hook_proc, which already dedupes via _is_down — harmless."""
        old = self._hook
        new = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, None, 0)
        if new:
            self._hook = new
            if old:
                user32.UnhookWindowsHookEx(old)
            log.debug("PTT hook refreshed")
        else:
            log.warning("PTT hook refresh failed — keeping previous handle")

    def run(self):
        self._tid = kernel32.GetCurrentThreadId()
        self._hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, None, 0)
        self._ready.set()
        if not self._hook:
            return
        timer_id = user32.SetTimer(None, 0, _REFRESH_MS, None)
        msg = wt.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            if msg.message == WM_TIMER and (not timer_id or msg.wParam == timer_id):
                self._reinstall_hook()
                continue
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        if timer_id:
            user32.KillTimer(None, timer_id)
        if self._hook:
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
