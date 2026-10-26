"""Double-click from Explorer to start FolderHub without a console window.

Windows Python's .pyw association uses pythonw.exe. The login-startup path in
startup.py already invokes pythonw.exe --no-browser directly.
"""
from __future__ import annotations

import ctypes
from pathlib import Path
import sys
import traceback
import urllib.request
import webbrowser

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from app import main
    if __name__ == "__main__":
        # A Windows login autostart may have launched this server already.
        # For a manual double-click, show that existing page instead of
        # trying to bind the same port and quitting without a visible error.
        running = False
        try:
            with urllib.request.urlopen("http://127.0.0.1:8765/api/config", timeout=0.45) as response:
                import json
                info = json.load(response)
                running = bool(info.get("token") and info.get("platform") == "win32")
        except (OSError, ValueError):
            pass
        if running:
            webbrowser.open("http://127.0.0.1:8765/")
            sys.exit(0)
        result = main()
        if result:
            raise RuntimeError("FolderHub 启动失败，可能是端口 8765 被其他程序占用")
        sys.exit(0)
except Exception:
    log = Path.home() / "FolderHub-startup-error.log"
    try:
        log.write_text(traceback.format_exc(), encoding="utf-8")
    except OSError:
        pass
    ctypes.windll.user32.MessageBoxW(None,
        "FolderHub 启动失败。请运行 start_windows.bat 查看错误详情。",
        "FolderHub", 0x10)
