"""Opt-in per-user Windows login autostart for FolderHub (no admin rights)."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "DailyToolsSet.FolderHub"


class StartupError(Exception):
    pass


def supported():
    return os.name == "nt"


def command_for(executable: Path, script: Path):
    """Build a Windows command line with proper quoting; no cmd.exe involved."""
    return subprocess.list2cmdline([str(executable), str(script), "--no-browser"])


def launch_command():
    if not supported():
        raise StartupError("开机自启动只支持 Windows")
    executable = Path(sys.executable).resolve()
    if executable.name.lower() not in ("python.exe", "pythonw.exe"):
        raise StartupError("无法定位 Python 启动程序，请使用 Windows 正式安装的 Python 运行")
    hidden = executable.with_name("pythonw.exe")
    if not hidden.is_file():
        raise StartupError("找不到 pythonw.exe，无法注册静默启动；请安装完整的 Windows Python")
    cmd = command_for(hidden, Path(__file__).resolve().parent / "app.py")
    if len(cmd) > 260:
        raise StartupError("启动命令超过 Windows Run 启动项长度限制（260 字符），请将项目放到更短的路径")
    return cmd


def _winreg():
    if not supported():
        raise StartupError("此操作仅支持 Windows")
    import winreg
    return winreg


def status():
    if not supported():
        return {"supported": False, "enabled": False}
    reg = _winreg()
    try:
        with reg.OpenKey(reg.HKEY_CURRENT_USER, RUN_KEY, 0, reg.KEY_READ) as key:
            command, _ = reg.QueryValueEx(key, VALUE_NAME)
    except FileNotFoundError:
        return {"supported": True, "enabled": False}
    try:
        expected = launch_command()
    except StartupError:
        expected = None
    return {"supported": True, "enabled": command == expected,
            "needs_update": command != expected}


def set_enabled(enabled):
    if type(enabled) is not bool:
        raise StartupError("自启动状态必须是 true 或 false")
    reg = _winreg()
    # Never touch machine-wide startup; only HKCU (current signed-in user).
    if enabled:
        command = launch_command()
        with reg.CreateKeyEx(reg.HKEY_CURRENT_USER, RUN_KEY, 0, reg.KEY_SET_VALUE) as key:
            reg.SetValueEx(key, VALUE_NAME, 0, reg.REG_SZ, command)
    else:
        try:
            with reg.OpenKey(reg.HKEY_CURRENT_USER, RUN_KEY, 0, reg.KEY_SET_VALUE) as key:
                reg.DeleteValue(key, VALUE_NAME)
        except FileNotFoundError:
            pass
    return status()
