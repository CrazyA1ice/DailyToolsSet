"""Native Windows notification-area controller for FolderHub.

No third-party modules, Windows service, administrator rights or public network bind.
The local HTTP service runs in a thread owned by the tray process and is cleanly shut
down before the tray exits. An independently started app.py is never killed by us.
"""
from __future__ import annotations

import argparse
import base64
import ntpath
import subprocess
import ctypes
from ctypes import wintypes
import json
import os
import tempfile
from pathlib import Path
import sys
from threading import Thread
from urllib.parse import quote
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError
import webbrowser

import app

PORT = 8765
SINGLE_INSTANCE = "Local\\DailyToolsSet.FolderHub.Tray.V1"
MENU_OPEN = 1001
MENU_RESTART = 1002
MENU_EXIT = 1003
MENU_QUICK = 1004
QUICK_ENTRY_BASE = 2000
HOTKEY_ID = 46
HOTKEY_MODIFIERS = 0x0001 | 0x0002 | 0x0004  # Alt + Ctrl + Shift
HOTKEY_VK = ord("F")
HOTKEY_LABEL = "Ctrl+Alt+Shift+F"
MENU_CAPTURE=1006
MENU_SHORTCUT=1005
MENU_KEY_BASE=3000
HOTKEY_OPTIONS=(
    ("Ctrl+Alt+Shift+F",0x0001|0x0002|0x0004,ord("F")),
    ("Ctrl+Alt+Shift+Q",0x0001|0x0002|0x0004,ord("Q")),
    ("Ctrl+Alt+Shift+S",0x0001|0x0002|0x0004,ord("S")),
    ("Ctrl+Shift+F",0x0002|0x0004,ord("F")),
    ("Ctrl+Alt+Space",0x0001|0x0002,0x20),
)
DEFAULT_HOTKEY=HOTKEY_OPTIONS[0][0]
MB_TOPMOST=0x40000
MB_SETFOREGROUND=0x10000


def read_hotkey(path):
    try:
        data=Path(path).read_bytes()
        if len(data)>256:return DEFAULT_HOTKEY
        setting=json.loads(data)
        key=setting.get("shortcut") if type(setting) is dict else None
        if key in {row[0] for row in HOTKEY_OPTIONS}:return key
    except (OSError,ValueError,TypeError):
        pass
    return DEFAULT_HOTKEY


def save_hotkey(path,choice):
    if choice not in {row[0] for row in HOTKEY_OPTIONS}:
        raise ValueError("不支持的快捷键组合")
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=None
    try:
        with tempfile.NamedTemporaryFile("w",encoding="utf-8",dir=path.parent,
                                         prefix=".hotkey-",suffix=".tmp",delete=False) as f:
            tmp=Path(f.name)
            json.dump({"shortcut":choice},f)
            f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if tmp is not None:tmp.unlink(missing_ok=True)


def server_is_folderhub(port=PORT):
    """Only consider the loopback service ours if it identifies as FolderHub."""
    try:
        with urlopen(f"http://127.0.0.1:{port}/api/config", timeout=0.5) as reply:
            payload = json.load(reply)
            return (isinstance(payload, dict) and bool(payload.get("token"))
                    and payload.get("platform") == "win32")
    except (OSError, ValueError, TimeoutError):
        return False


def safe_menu_title(value, limit=46):
    """Never treat saved resource names as Win32 menu mnemonics or new lines."""
    text = "".join(char if char.isprintable() and char not in "\r\n" else " "
                   for char in str(value or ""))
    text = " ".join(text.split())
    safe, consumed = [], 0
    for char in text:
        token = "&&" if char == "&" else char
        if sum(len(bit) for bit in safe) + len(token) > limit:
            break
        safe.append(token)
        consumed += 1
    return "".join(safe) + ("…" if consumed < len(text) else "")


def build_quick_entries(nodes,recent,workspaces):
    """Bounded unified navigation. Only IDs, never raw targets, leave this layer.

    The existing authenticated /api/nodes/<id>/open route makes the final
    decision whether a folder, document or website can be opened.
    """
    candidates=[]
    for item in nodes:
        if type(item) is not dict or type(item.get("id")) is not int:
            continue
        kind=item.get("resource_kind","folder")
        if kind == "folder":
            if not item.get("folder_path"):
                continue
            label=safe_menu_title(item.get("title"))
        elif kind in ("file","url") and item.get("node_type") == "leaf":
            if not item.get("resource_target"):
                continue
            label=("📄 " if kind=="file" else "🌐 ")+safe_menu_title(item.get("title"),42)
        else:
            continue
        candidates.append((kind,{"kind":"folder","target":item["id"],"label":label}))
    # Prefer a small number of each newer resource kind so an existing
    # collection of dozens of folders cannot hide every saved file/URL.
    reserved=set()
    for kind in ("file","url"):
        reserved.update(index for index,(item_kind,_) in enumerate(candidates)
                        if item_kind==kind and
                        sum(1 for prior,_ in candidates[:index] if prior==kind)<2)
    for index in range(len(candidates)):
        if len(reserved)>=8:
            break
        reserved.add(index)
    resources=[entry for index,(_,entry) in enumerate(candidates) if index in reserved]
    entries=([{"kind":"heading","label":"快速打开资源"}]+resources) if resources else []
    groups=[{"kind":"workspace","target":item["name"],
             "label":safe_menu_title(item["name"])}
            for item in workspaces[:8] if type(item) is dict
            and type(item.get("name")) is str and item["name"]]
    if groups:
        entries.append({"kind":"heading","label":"项目工作区"})
        entries.extend(groups)
    return entries


def explorer_directory_for_hwnd(hwnd, *, run=None):
    """Read a *specific* Explorer window through built-in PowerShell ShellWindows COM.

    Only a numeric foreground Explorer HWND is inserted into the constant script,
    never user text. ShellWindows may expose another tab on some Windows 11
    builds: the user must inspect the exact returned directory before saving.
    """
    if type(hwnd) is not int or hwnd <= 0:
        raise ValueError("资源管理器窗口句柄无效")
    script = f"""
$ErrorActionPreference = 'Stop'
$target = [long]{hwnd}
$shell = New-Object -ComObject Shell.Application
foreach ($window in @($shell.Windows())) {{
    try {{
        if ([long]$window.HWND -ne $target) {{ continue }}
        $folder = [string]$window.Document.Folder.Self.Path
        if ($folder -and [IO.Path]::IsPathRooted($folder) -and
            (Test-Path -LiteralPath $folder -PathType Container)) {{
            [Console]::Out.Write([Convert]::ToBase64String(
                [Text.Encoding]::Unicode.GetBytes($folder)))
            break
        }}
    }} catch {{ continue }}
}}
"""
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    runner = run or subprocess.run
    try:
        process = runner(["powershell.exe", "-NoProfile", "-NonInteractive",
                          "-EncodedCommand", encoded],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         stdin=subprocess.DEVNULL, timeout=7, check=False,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError("无法读取资源管理器窗口，请确认 Windows PowerShell 可用") from error
    if process.returncode != 0 or not process.stdout.strip():
        raise RuntimeError("未能识别当前资源管理器的真实目录；请尝试使用单独窗口，或在网页中手动添加")
    try:
        path = base64.b64decode(process.stdout.strip(), validate=True).decode("utf-16-le")
    except (ValueError, UnicodeError) as error:
        raise RuntimeError("读取的资源管理器路径编码无效") from error
    if not ntpath.isabs(path) or "\\x00" in path:
        raise RuntimeError("当前窗口不是可以收藏的文件系统目录")
    return path


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

    @property
    def hotkey_file(self):
        return (self.data_dir or app.data_directory())/"hotkey.json"

    def quick_entries(self):
        if self.server is not None:
            store = self.server.store
            return build_quick_entries(
                store.all(), [],
                store.preferences.get()["settings"]["workspaces"])
        # The tray must not take ownership of or restart an external service.
        if not self.external:
            raise RuntimeError("FolderHub 本地服务尚未启动")
        if not server_is_folderhub(self.port):
            raise RuntimeError("独立 FolderHub 服务未响应，请检查服务状态")
        def get(path):
            with urlopen(f"{self.url.rstrip('/')}{path}", timeout=1.5) as reply:
                return json.load(reply)
        return build_quick_entries(
            get("/api/nodes")["nodes"],
            [],
            get("/api/preferences")["settings"]["workspaces"])

    def open_quick_folder(self, node_id):
        """Use the existing authenticated node ID endpoint, never shell a path."""
        if type(node_id) is not int or node_id <= 0:
            raise ValueError("模块 ID 无效")
        with urlopen(f"{self.url.rstrip('/')}/api/config", timeout=1.5) as reply:
            config = json.load(reply)
        if not (type(config) is dict and config.get("platform") == "win32" and
                isinstance(config.get("token"), str) and config["token"]):
            raise RuntimeError("未能确认 FolderHub 本地服务")
        request = Request(
            f"{self.url.rstrip('/')}/api/nodes/{node_id}/open", data=b"{}",
            headers={"Content-Type": "application/json",
                     "X-FolderHub-Token": config["token"]},
            method="POST")
        try:
            with urlopen(request, timeout=3) as reply:
                result = json.load(reply)
        except HTTPError as error:
            try:
                detail = json.load(error).get("error", str(error))
            except (ValueError, OSError):
                detail = str(error)
            raise RuntimeError(detail) from error
        if not result.get("ok"):
            raise RuntimeError("文件夹打开请求未成功")
        return result

    def capture_current_directory(self, folder_path):
        """Save a user-confirmed Explorer path via the existing local auth model."""
        if type(folder_path) is not str or not ntpath.isabs(folder_path):
            raise ValueError("收藏路径必须来自有效的绝对 Windows 文件夹")
        if any(ord(c) < 32 for c in folder_path):
            raise ValueError("文件夹路径不能包含控制字符")
        with urlopen(f"{self.url.rstrip('/')}/api/config", timeout=1.5) as reply:
            config = json.load(reply)
        if not (type(config) is dict and config.get("platform") == "win32"
                and isinstance(config.get("token"), str) and config["token"]):
            raise RuntimeError("未能确认 FolderHub 本地服务")
        payload = json.dumps({"folder_path":folder_path},ensure_ascii=False).encode("utf-8")
        request = Request(f"{self.url.rstrip('/')}/api/quick-capture", data=payload,
                          headers={"Content-Type": "application/json",
                                   "X-FolderHub-Token": config["token"]},
                          method="POST")
        try:
            with urlopen(request,timeout=6) as reply:
                return json.load(reply)
        except HTTPError as error:
            try:
                message=json.load(error).get("error",str(error))
            except (ValueError,OSError):
                message=str(error)
            raise RuntimeError(message) from error

    def open_quick_workspace(self, name):
        if type(name) is not str or not name:
            raise ValueError("工作区名称无效")
        webbrowser.open(self.url + "#workspace/" + quote(name, safe=""))

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
    WM_HOTKEY = 0x0312
    MOD_NOREPEAT = 0x4000
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
        self.hotkey_registered = False
        self.hotkey_choice=DEFAULT_HOTKEY
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
        u.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        u.RegisterHotKey.restype = wintypes.BOOL
        u.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        u.UnregisterHotKey.restype = wintypes.BOOL
        u.GetForegroundWindow.restype = wintypes.HWND
        u.GetClassNameW.argtypes = [wintypes.HWND, ctypes.c_wchar_p, ctypes.c_int]
        u.GetClassNameW.restype = ctypes.c_int
        u.MessageBoxW.argtypes = [wintypes.HWND, wintypes.LPCWSTR,
                                  wintypes.LPCWSTR, wintypes.UINT]
        u.MessageBoxW.restype = ctypes.c_int
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

    def _register_hotkey(self):
        self.hotkey_choice=read_hotkey(self.controller.hotkey_file)
        _,modifiers,key=next(item for item in HOTKEY_OPTIONS
                             if item[0]==self.hotkey_choice)
        self.hotkey_registered=bool(self.user32.RegisterHotKey(
            self.hwnd,HOTKEY_ID,modifiers|self.MOD_NOREPEAT,key))
        if not self.hotkey_registered:
            print("[FolderHub] shortcut unavailable:",self.hotkey_choice,file=sys.stderr)

    def _remove_hotkey(self):
        if self.hotkey_registered and self.hwnd:
            self.user32.UnregisterHotKey(self.hwnd,HOTKEY_ID)
            self.hotkey_registered=False

    def _set_hotkey(self,choice):
        previous=self.hotkey_choice
        if choice==previous and self.hotkey_registered:return
        # Persist before releasing the currently working registration.
        save_hotkey(self.controller.hotkey_file,choice)
        self._remove_hotkey()
        try:
            self._register_hotkey()
        except Exception:
            save_hotkey(self.controller.hotkey_file,previous)
            self._register_hotkey()
            raise
        if not self.hotkey_registered:
            save_hotkey(self.controller.hotkey_file,previous)
            self._register_hotkey()
            self._message("新快捷键被占用，已尝试恢复之前的快捷键")

    def _show_hotkey_settings(self):
        menu=self.user32.CreatePopupMenu()
        if not menu:return
        try:
            for index,(label,_,_) in enumerate(HOTKEY_OPTIONS):
                self.user32.AppendMenuW(menu,0,MENU_KEY_BASE+index,
                    ("✓ " if label==self.hotkey_choice else "　")+label)
            pos=wintypes.POINT()
            self.user32.GetCursorPos(ctypes.byref(pos))
            self.user32.SetForegroundWindow(self.hwnd)
            choice=self.user32.TrackPopupMenu(menu,0x0100|0x0002,
                 pos.x,pos.y,0,self.hwnd,None)
            self.user32.PostMessageW(self.hwnd,0,0,0)
            if MENU_KEY_BASE<=choice<MENU_KEY_BASE+len(HOTKEY_OPTIONS):
                self._set_hotkey(HOTKEY_OPTIONS[choice-MENU_KEY_BASE][0])
        finally:
            self.user32.DestroyMenu(menu)

    def _capture_explorer_directory(self,foreground=None):
        if foreground is None:foreground=self.user32.GetForegroundWindow()
        if not foreground:
            raise RuntimeError("请先切换到需要收藏的 Windows 资源管理器窗口")
        name=ctypes.create_unicode_buffer(128)
        if not self.user32.GetClassNameW(foreground,name,len(name)) or name.value not in (
                "CabinetWClass","ExploreWClass"):
            raise RuntimeError("仅支持资源管理器中的当前文件夹，请先激活资源管理器窗口")
        return explorer_directory_for_hwnd(int(foreground))

    def _capture_current_folder(self,foreground=None):
        try:
            folder=self._capture_explorer_directory(foreground)
        except (OSError, ValueError, RuntimeError) as error:
            self._message(str(error))
            return
        # Explicit path confirmation matters for Windows 11 multi-tab Explorer,
        # where ShellWindows COM may expose a non-active tab for the same HWND.
        reply=self.user32.MessageBoxW(
            self.hwnd,
            "将以下文件夹加入 FolderHub 导航？\n\n" + folder +
            "\n\n若与资源管理器当前显示的路径不一致，请选「否」。"
            "\n该操作只添加快捷导航，不会复制或移动实际文件。",
            "确认快速收录", 0x00000004 | 0x00000020 | 0x00000100 |
            MB_TOPMOST | MB_SETFOREGROUND)
        if reply!=6:  # IDYES; default button is NO.
            return
        try:
            result=self.controller.capture_current_directory(folder)
            self._message("已收录目录：" + folder if result.get("created")
                          else "此目录已在导航中：" + folder)
        except (OSError, ValueError, RuntimeError) as error:
            self._message("快速收录失败：" + str(error))

    def _remove_icon(self):
        if self.icon_added and self.hwnd:
            self.shell32.Shell_NotifyIconW(self.NIM_DELETE, ctypes.byref(self._icon_data()))
            self.icon_added = False

    def _message(self, message, title="FolderHub"):
        self.user32.MessageBoxW(self.hwnd, message, title,
                               0x40 | MB_TOPMOST | MB_SETFOREGROUND)

    def _show_menu(self):
        menu = self.user32.CreatePopupMenu()
        if not menu:
            return
        try:
            self.user32.AppendMenuW(menu, 0x0001 | 0x0002, 0, self.controller.status)
            self.user32.AppendMenuW(menu, 0x0800, 0, None)  # MF_SEPARATOR
            self.user32.AppendMenuW(menu, 0, MENU_OPEN, "打开 FolderHub")
            self.user32.AppendMenuW(menu, 0, MENU_QUICK,
                                    "功能菜单 (" + self.hotkey_choice + ")"
                                    if self.hotkey_registered else "功能菜单（快捷键不可用）")
            self.user32.AppendMenuW(menu,0,MENU_SHORTCUT,"设置全局快捷键…")
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
            elif selection == MENU_QUICK:
                self._show_quick_menu()
            elif selection == MENU_SHORTCUT:
                self._show_hotkey_settings()
            elif selection == MENU_RESTART and not self.controller.external:
                try:
                    self.controller.restart()
                except Exception as error:
                    self._message(f"重启失败：{error}")
            elif selection == MENU_EXIT:
                self.user32.DestroyWindow(self.hwnd)
        finally:
            self.user32.DestroyMenu(menu)

    def _show_quick_menu(self):
        capture_hwnd=self.user32.GetForegroundWindow()
        try:
            entries = self.controller.quick_entries()
        except (OSError, ValueError, RuntimeError, KeyError, TypeError) as error:
            self._message(f"无法读取快捷入口：{error}")
            return
        menu = self.user32.CreatePopupMenu()
        if not menu:
            return
        lookup = {}
        try:
            self.user32.AppendMenuW(menu, 0x0001 | 0x0002, 0,
                                    "FolderHub · 快捷导航")
            self.user32.AppendMenuW(menu, 0x0800, 0, None)
            for item in entries:
                if item["kind"] == "heading":
                    if lookup:
                        self.user32.AppendMenuW(menu, 0x0800, 0, None)
                    self.user32.AppendMenuW(menu, 0x0001 | 0x0002, 0, item["label"])
                    continue
                command = QUICK_ENTRY_BASE + len(lookup)
                lookup[command] = item
                self.user32.AppendMenuW(menu, 0, command, item["label"])
            if not lookup:
                self.user32.AppendMenuW(menu, 0x0001 | 0x0002, 0,
                                        "暂无已绑定文件夹或项目工作区")
            self.user32.AppendMenuW(menu, 0x0800, 0, None)
            self.user32.AppendMenuW(menu,0,MENU_CAPTURE,"＋ 收录当前资源管理器目录…")
            self.user32.AppendMenuW(menu, 0, MENU_OPEN, "打开完整工作台…")
            position = wintypes.POINT()
            self.user32.GetCursorPos(ctypes.byref(position))
            self.user32.SetForegroundWindow(self.hwnd)
            choice = self.user32.TrackPopupMenu(
                menu, 0x0100 | 0x0002, position.x, position.y, 0,
                self.hwnd, None)
            self.user32.PostMessageW(self.hwnd, 0, 0, 0)
            if choice == MENU_OPEN:
                webbrowser.open(self.controller.url)
            elif choice == MENU_CAPTURE:
                self._capture_current_folder(capture_hwnd)
            elif choice in lookup:
                selected = lookup[choice]
                try:
                    if selected["kind"] == "folder":
                        self.controller.open_quick_folder(selected["target"])
                    elif selected["kind"] == "workspace":
                        self.controller.open_quick_workspace(selected["target"])
                except (OSError, ValueError, RuntimeError, URLError) as error:
                    self._message(f"快捷入口打开失败：{error}")
        finally:
            self.user32.DestroyMenu(menu)

    def _window_proc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == self.WM_HOTKEY and wparam == HOTKEY_ID:
                self._show_quick_menu()
                return 0
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
            self._register_hotkey()
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
            self._remove_hotkey()
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
