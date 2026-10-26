"""Open a Windows folder and best-effort activate its Explorer window.

Only Windows standard-library APIs are used; never run arbitrary shell commands.
Windows' foreground-lock rules and Explorer tabs prevent an absolute guarantee.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from pathlib import PureWindowsPath
import time

EXPLORER_CLASSES = {"CabinetWClass", "ExploreWClass"}
SW_RESTORE = 9
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2


def _user32():
    user32 = ctypes.windll.user32
    user32.IsWindowVisible.argtypes = (wintypes.HWND,)
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetClassNameW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    user32.GetClassNameW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
    user32.ShowWindow.restype = wintypes.BOOL
    user32.SetWindowPos.argtypes = (wintypes.HWND, wintypes.HWND,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, wintypes.UINT)
    user32.SetWindowPos.restype = wintypes.BOOL
    user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
    user32.SetForegroundWindow.restype = wintypes.BOOL
    return user32


def _windows(user32=None):
    """Map Explorer top-level HWND -> title; return an empty map on UI API errors."""
    if os.name != "nt":
        return {}
    user32 = user32 or _user32()
    found = {}
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = (callback_type, wintypes.LPARAM)
    user32.EnumWindows.restype = wintypes.BOOL

    def visit(handle, unused):
        if not user32.IsWindowVisible(handle):
            return True
        cls = ctypes.create_unicode_buffer(128)
        user32.GetClassNameW(handle, cls, len(cls))
        if cls.value not in EXPLORER_CLASSES:
            return True
        title = ctypes.create_unicode_buffer(1024)
        user32.GetWindowTextW(handle, title, len(title))
        found[int(handle)] = title.value
        return True

    callback = callback_type(visit)
    user32.EnumWindows(callback, 0)
    return found


def _best_match(before, after, folder):
    """Prefer newly created Explorer windows, falling back to a folder-named tab."""
    name = PureWindowsPath(folder.rstrip("\\/")).name.casefold()
    if not name:
        return None
    candidates = []
    for hwnd, title in after.items():
        clean = title.casefold().strip()
        exact = clean == name or clean.startswith(name + " - ")
        if exact and hwnd not in before:
            candidates.append((0, hwnd))
        elif exact:
            candidates.append((1, hwnd))
        elif hwnd not in before and not clean:
            # Windows may create the Explorer HWND before its title is ready.
            candidates.append((2, hwnd))
    return min(candidates)[1] if candidates else None


def _raise_window(hwnd, user32=None):
    user32 = user32 or _user32()
    # A temporary TOPMOST -> NOTOPMOST transition raises Explorer without
    # leaving it pinned above every other application.
    flags = SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE
    user32.ShowWindow(hwnd, SW_RESTORE)
    user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, flags)
    user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, flags)
    user32.SetForegroundWindow(hwnd)


def open_and_focus(folder, *, opener=None, list_windows=None, focus=None, sleep=None):
    """Launch folder, then try to promote a matching Explorer HWND.

    Never fail opening because the OS refuses to grant foreground focus.
    The returned bool reports whether a focus attempt was made, not a guarantee.
    """
    opener = opener or os.startfile
    list_windows = list_windows or _windows
    focus = focus or _raise_window
    sleep = sleep or time.sleep
    try:
        previous = list_windows()
    except Exception:
        previous = {}
    opener(folder)  # Native ShellExecute from os.startfile
    for interval in (0.10, 0.16, 0.22, 0.28, 0.35):
        sleep(interval)
        try:
            hwnd = _best_match(previous, list_windows(), folder)
            if hwnd is not None:
                focus(hwnd)
                return True
        except (OSError, AttributeError, ValueError):
            # Opening succeeded; foreground activation is only a courtesy.
            return False
    return False
