"""Native Windows notification-area controller for FolderHub.

No third-party modules, Windows service, administrator rights or public network bind.
The local HTTP service runs in a thread owned by the tray process and is cleanly shut
down before the tray exits. An independently started app.py is never killed by us.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import sys
from threading import Thread
from urllib.request import urlopen
import webbrowser

import app

PORT = 8765
SINGLE_INSTANCE = "Local\\DailyToolsSet.FolderHub.Tray.V1"
MENU_OPEN = 1001
MENU_RESTART = 1002
MENU_EXIT = 1003


def server_is_folderhub(port=PORT):
    """Only consider the loopback service ours if it identifies as FolderHub."""
    try:
        with urlopen(f"http://127.0.0.1:{port}/api/config", timeout=0.5) as reply:
            payload = json.load(reply)
            return (isinstance(payload, dict) and bool(payload.get("token"))
                    and payload.get("platform") == "win32")
    except (OSError, ValueError, TimeoutError):
        return False


class ServiceController:
    """The tray owns its server; never terminate an independently started process."""

    def __init__(self, port=PORT, data_dir=None):
        self.port = port
        self.data_dir = Path(data_dir) if data_dir is not None else None
        self.server = None
        self.thread = None
        self.external = False

    @property
    def url(self):
        return f"http://127.0.0.1:{self.port}/"

    @property
    def status(self):
        return "已连接独立运行的服务" if self.external else (
            "运行中" if self.server is not None else "已停止")

    def start(self):
        if self.server is not None:
            return
        if self.port and server_is_folderhub(self.port):
            self.external = True
            return
        location = self.data_dir or app.data_directory()
        default = self.data_dir is None and not os.environ.get("FOLDERHUB_DATA_DIR")
        if default:
            app.migrate_legacy_database(location)
        uploads = app.PORTABLE_UPLOADS if default else location / "uploads"
        store = app.Store(location / "folderhub.db", uploads_dir=uploads)
        # If another process owns the port (and is not FolderHub) the bind fails
        # instead of silently serving the wrong site or terminating that process.
        server = app.FolderServer(("127.0.0.1", self.port), store)
        self.server = server
        self.port = server.server_port
        self.external = False
        self.thread = Thread(target=server.serve_forever, name="FolderHubHTTP", daemon=True)
        self.thread.start()

    def stop(self):
        if self.server is None:
            return
        server, thread = self.server, self.thread
        try:
            server.shutdown()    # Calls shutdown() from a different thread.
            if thread is not None:
                thread.join(timeout=5)
        finally:
            server.server_close()
            self.server = None
            self.thread = None

    def restart(self):
        if self.external:
            raise RuntimeError("当前服务由独立进程启动，托盘不能重启或关闭它")
        self.stop()
        self.start()


class WindowsTray:
    WM_TRAY = 0x8000 + 24
    WM_CLOSE = 0x0010
    WM_DESTROY = 0x0002
    WM_LBUTTONDBLCLK = 0x0203
    WM_RBUTTONUP = 0x0205
    WM_CONTEXTMENU = 0x007B
    NIM_ADD = 0
    NIM_DELETE = 2
    NIF_MESSAGE = 1
    NIF_ICON = 2
    NIF_TIP = 4

    def __init__(self, controller):
        if os.name != "nt":
            raise RuntimeError("系统托盘功能仅支持 Windows")
        self.controller = controller
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._setup_windows_types()
        self.hwnd = None
        self.icon_added = False
        self._callback = self.WNDPROC(self._window_proc)  # Hold callback for whole loop.
        self.taskbar_created = self.user32.RegisterWindowMessageW("TaskbarCreated")

    def _setup_windows_types(self):
        self.WNDPROC = ctypes.WINFUNCTYPE(
            ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT,
            wintypes.WPARAM, wintypes.LPARAM)

        class WNDCLASSW(ctypes.Structure):
            _fields_ = [
                ("style", wintypes.UINT), ("lpfnWndProc", self.WNDPROC),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HCURSOR), ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]
        self.WNDCLASSW = WNDCLASSW

        class NOTIFYICONDATAW(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND),
                ("uID", wintypes.UINT), ("uFlags", wintypes.UINT),
                ("uCallbackMessage", wintypes.UINT), ("hIcon", wintypes.HICON),
                ("szTip", wintypes.WCHAR * 128),
                ("dwState", wintypes.DWORD), ("dwStateMask", wintypes.DWORD),
                ("szInfo", wintypes.WCHAR * 256),
                ("uTimeoutOrVersion", wintypes.UINT),
                ("szInfoTitle", wintypes.WCHAR * 64),
                ("dwInfoFlags", wintypes.DWORD),
                ("guidItem", wintypes.BYTE * 16),
                ("hBalloonIcon", wintypes.HICON)]
        self.NOTIFYICONDATAW = NOTIFYICONDATAW
        u, s, k = self.user32, self.shell32, self.kernel32
        u.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
        u.RegisterClassW.restype = wintypes.WORD
        u.CreateWindowExW.argtypes = [
            wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, ctypes.c_void_p]
        u.CreateWindowExW.restype = wintypes.HWND
        u.DefWindowProcW.argtypes = [
            wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        u.DefWindowProcW.restype = ctypes.c_ssize_t
        u.LoadIconW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]
        u.LoadIconW.restype = wintypes.HICON
        u.RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
        u.RegisterWindowMessageW.restype = wintypes.UINT
        u.GetMessageW.argtypes = [
            ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
        u.GetMessageW.restype = ctypes.c_int
        u.CreatePopupMenu.restype = wintypes.HMENU
        u.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR]
        u.TrackPopupMenu.argtypes = [
            wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int,
            ctypes.c_int, wintypes.HWND, ctypes.c_void_p]
        u.TrackPopupMenu.restype = wintypes.UINT
        u.DestroyMenu.argtypes = [wintypes.HMENU]
        u.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
        u.DestroyWindow.argtypes = [wintypes.HWND]
        u.SetForegroundWindow.argtypes = [wintypes.HWND]
        u.PostMessageW.argtypes = [
            wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        s.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
        s.Shell_NotifyIconW.restype = wintypes.BOOL
        k.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        k.GetModuleHandleW.restype = wintypes.HMODULE

    def _icon_data(self):
        data = self.NOTIFYICONDATAW()
        data.cbSize = ctypes.sizeof(data)
        data.hWnd = self.hwnd
        data.uID = 1
        data.uFlags = self.NIF_MESSAGE | self.NIF_ICON | self.NIF_TIP
        data.uCallbackMessage = self.WM_TRAY
        # Standard Windows application glyph; no .ico dependency.
        resource = ctypes.cast(ctypes.c_void_p(32512), wintypes.LPCWSTR)
        data.hIcon = self.user32.LoadIconW(None, resource)
        data.szTip = "FolderHub · 本地文件导航"
        return data

    def _add_icon(self):
        data = self._icon_data()
        if not self.shell32.Shell_NotifyIconW(self.NIM_ADD, ctypes.byref(data)):
            raise OSError("无法在 Windows 系统托盘中创建 FolderHub 图标")
        self.icon_added = True

    def _remove_icon(self):
        if self.icon_added and self.hwnd:
            self.shell32.Shell_NotifyIconW(self.NIM_DELETE, ctypes.byref(self._icon_data()))
            self.icon_added = False

    def _message(self, message, title="FolderHub"):
        self.user32.MessageBoxW(self.hwnd, message, title, 0x40)

    def _show_menu(self):
        menu = self.user32.CreatePopupMenu()
        if not menu:
            return
        try:
            self.user32.AppendMenuW(menu, 0x0001 | 0x0002, 0, self.controller.status)
            self.user32.AppendMenuW(menu, 0x0800, 0, None)  # MF_SEPARATOR
            self.user32.AppendMenuW(menu, 0, MENU_OPEN, "打开 FolderHub")
            self.user32.AppendMenuW(menu, 0x0001 if self.controller.external else 0,
                                    MENU_RESTART, "重启服务")
            self.user32.AppendMenuW(menu, 0x0800, 0, None)
            self.user32.AppendMenuW(menu, 0, MENU_EXIT,
                                    "退出托盘（独立服务保留）" if self.controller.external
                                    else "退出 FolderHub")
            pos = wintypes.POINT()
            self.user32.GetCursorPos(ctypes.byref(pos))
            self.user32.SetForegroundWindow(self.hwnd)
            selection = self.user32.TrackPopupMenu(
                menu, 0x0100 | 0x0002, pos.x, pos.y, 0, self.hwnd, None)
            self.user32.PostMessageW(self.hwnd, 0, 0, 0)
            if selection == MENU_OPEN:
                webbrowser.open(self.controller.url)
            elif selection == MENU_RESTART and not self.controller.external:
                try:
                    self.controller.restart()
                except Exception as error:
                    self._message(f"重启失败：{error}")
            elif selection == MENU_EXIT:
                self.user32.DestroyWindow(self.hwnd)
        finally:
            self.user32.DestroyMenu(menu)

    def _window_proc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == self.WM_TRAY:
                if lparam == self.WM_LBUTTONDBLCLK:
                    webbrowser.open(self.controller.url)
                elif lparam in (self.WM_RBUTTONUP, self.WM_CONTEXTMENU):
                    self._show_menu()
                return 0
            if msg == self.taskbar_created:
                self.icon_added = False
                self._add_icon()  # Windows Explorer restarted.
                return 0
            if msg == self.WM_CLOSE:
                self.user32.DestroyWindow(hwnd)
                return 0
            if msg == self.WM_DESTROY:
                self.user32.PostQuitMessage(0)
                return 0
        except Exception as error:
            # Never let a Python exception escape into a Win32 WNDPROC callback.
            try:
                self._message(f"托盘操作失败：{error}")
            except Exception:
                pass
            return 0
        return self.user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def run(self, open_browser=True):
        u = self.user32
        hinstance = self.kernel32.GetModuleHandleW(None)
        class_name = "DailyToolsSet_FolderHubTrayWindow"
        wc = self.WNDCLASSW()
        wc.lpfnWndProc = self._callback
        wc.hInstance = hinstance
        wc.lpszClassName = class_name
        if not u.RegisterClassW(ctypes.byref(wc)):
            raise OSError("注册 FolderHub 托盘窗口失败")
        self.hwnd = u.CreateWindowExW(
            0, class_name, "FolderHub Tray", 0, 0, 0, 0, 0, None, None, hinstance, None)
        if not self.hwnd:
            raise OSError("创建 FolderHub 托盘窗口失败")
        try:
            self.controller.start()
            self._add_icon()
            if open_browser:
                webbrowser.open(self.controller.url)
            message = wintypes.MSG()
            while True:
                result = u.GetMessageW(ctypes.byref(message), None, 0, 0)
                if result == 0:
                    break
                if result < 0:
                    raise OSError("Windows 托盘消息循环失败")
                u.TranslateMessage(ctypes.byref(message))
                u.DispatchMessageW(ctypes.byref(message))
        finally:
            self._remove_icon()
            self.controller.stop()
            u.DestroyWindow(self.hwnd)


def acquire_single_instance():
    """Per-login-session mutex: repeated manual launches open the existing page."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateMutexW(None, False, SINGLE_INSTANCE)
    if not handle:
        raise OSError("无法创建 FolderHub 单实例锁")
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        kernel.CloseHandle(handle)
        return None
    return handle


def main(argv=None):
    if os.name != "nt":
        raise RuntimeError("系统托盘仅在 Windows 上可用")
    parser = argparse.ArgumentParser(description="FolderHub Windows 托盘控制器")
    parser.add_argument("--no-browser", action="store_true",
                        help="只启动托盘和服务，不主动打开浏览器")
    args = parser.parse_args(argv)
    lock = acquire_single_instance()
    if lock is None:
        if not args.no_browser:
            webbrowser.open(f"http://127.0.0.1:{PORT}/")
        return 0
    try:
        WindowsTray(ServiceController()).run(open_browser=not args.no_browser)
        return 0
    finally:
        kernel = ctypes.WinDLL("kernel32")
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle(lock)


if __name__ == "__main__":
    sys.exit(main())
