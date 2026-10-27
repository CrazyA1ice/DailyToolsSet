"""Double-click FolderHub without a console; now managed by a Windows tray icon.

Double-click when the tray already exists simply opens the existing dashboard.
The system login startup invokes this file with --no-browser.
"""
from __future__ import annotations

import ctypes
from pathlib import Path
import sys
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from tray import main

    if __name__ == "__main__":
        sys.exit(main())
except Exception:
    try:
        (Path.home() / "FolderHub-startup-error.log").write_text(
            traceback.format_exc(), encoding="utf-8")
    except OSError:
        pass
    if sys.platform == "win32":
        ctypes.windll.user32.MessageBoxW(
            None, "FolderHub 启动失败。请查看用户主目录中的 FolderHub-startup-error.log，"
            "或者使用 start_windows.bat 调试。", "FolderHub", 0x10)
    else:
        raise
