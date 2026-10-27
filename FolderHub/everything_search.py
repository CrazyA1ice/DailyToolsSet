"""Optional Everything ES CLI bridge. No disk index, shell, or Internet access."""
from __future__ import annotations

import ntpath
import os
from pathlib import Path
import shutil
import subprocess


class EverythingUnavailable(RuntimeError):
    pass


MAX_RESULTS = 30


def find_es():
    configured = os.environ.get("FOLDERHUB_ES_PATH", "").strip()
    if configured:
        binary = Path(configured)
        if binary.is_file() and binary.name.lower() == "es.exe":
            return str(binary)
        raise EverythingUnavailable("配置的 FOLDERHUB_ES_PATH 不是有效的 es.exe")
    binary = shutil.which("es.exe")
    if binary:
        return binary
    raise EverythingUnavailable(
        "未检测到 Everything 的 es.exe；请先安装并运行 Everything，"
        "将 ES 工具放入 PATH，或配置 FOLDERHUB_ES_PATH")


def search(query, *, run=None, executable=None):
    if (not isinstance(query, str) or not 2 <= len(query.strip()) <= 100
            or any(ord(char) < 32 or ord(char) == 127 for char in query)):
        raise ValueError("搜索词需要 2—100 字符且不能包含控制字符")
    es = executable or find_es()
    runner = run or subprocess.run
    args = [es, "-n", str(MAX_RESULTS), "-full-path",
            "-no-folder-append-path-separator", "--", query.strip()]
    try:
        result = runner(args, capture_output=True, text=True,
                        errors="replace", timeout=4, check=False,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise EverythingUnavailable("Everything 搜索超时或无法启动 es.exe") from exc
    if result.returncode != 0:
        raise EverythingUnavailable(
            "Everything 无法查询：请确认 Everything 已运行，且 es.exe 与之兼容")
    paths, seen = [], set()
    unavailable = 0
    for row in result.stdout.splitlines():
        path = row.strip()
        key = ntpath.normcase(ntpath.normpath(path))
        if (not ntpath.isabs(path) or any(ord(c) < 32 for c in path)
                or len(path) > 2048 or key in seen):
            continue
        seen.add(key)
        # Everything can still have stale, disconnected or offline index
        # entries. Do not misclassify a missing directory as a file.
        if os.path.isdir(path):
            kind = "folder"
        elif os.path.isfile(path):
            kind = "file"
        else:
            unavailable += 1
            continue
        paths.append({"path": path, "name": ntpath.basename(path) or path,
                      "kind": kind})
        if len(paths) == MAX_RESULTS:
            break
    return {"items": paths, "source": "Everything", "limit": MAX_RESULTS,
            "unavailable": unavailable}
