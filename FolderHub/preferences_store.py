"""Portable, atomic and validated FolderHub presentation preferences."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from threading import RLock

DEFAULTS = {
    'font': 'large', 'density': 'comfortable', 'sidebar': 'normal',
    'columns': 'auto', 'accent': 'blue', 'showCovers': True,
    'coverHeight': 'normal', 'coverFit': 'cover', 'sidebarCollapsed': False,
    'theme': 'cloud', 'layout': 'grid', 'expanded': None,
}
CHOICES = {
    'font': ('normal', 'large', 'xlarge'),
    'density': ('comfortable', 'compact'),
    'sidebar': ('normal', 'wide'),
    'columns': ('auto', '2', '3', '4'),
    'accent': ('blue', 'purple', 'teal', 'orange', 'rose'),
    'coverHeight': ('short', 'normal', 'tall'),
    'coverFit': ('cover', 'contain'),
    'theme': ('cloud', 'midnight', 'forest', 'aurora', 'sand', 'graphite', 'system'),
    'layout': ('grid', 'list'),
}
BOOLEAN_KEYS = frozenset(('showCovers', 'sidebarCollapsed'))
MAX_EXPANDED = 20000
MAX_BYTES = 128 * 1024


class PreferenceError(ValueError):
    pass


def validate(value):
    """Validate a complete/partial settings object without coercing or trusting unknown keys."""
    if not isinstance(value, dict) or set(value) - set(DEFAULTS):
        raise PreferenceError('个性化设置格式或字段无效')
    result = dict(DEFAULTS)
    for key, item in value.items():
        if key in CHOICES:
            if type(item) is not str or item not in CHOICES[key]:
                raise PreferenceError('个性化设置选项无效：' + key)
        elif key in BOOLEAN_KEYS:
            if type(item) is not bool:
                raise PreferenceError('个性化设置开关无效：' + key)
        elif key == 'expanded':
            if item is not None and (not isinstance(item, list) or len(item) > MAX_EXPANDED
                                    or any(type(n) is not int or n < 1 for n in item)
                                    or len(set(item)) != len(item)):
                raise PreferenceError('目录树展开状态无效')
        result[key] = item
    return result


class PreferencesStore:
    def __init__(self, path):
        self.path = Path(path)
        self._lock = RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self):
        if not self.path.exists():
            return None
        try:
            raw = self.path.read_bytes()
            if len(raw) > MAX_BYTES:
                raise PreferenceError('个性化设置文件过大')
            value = json.loads(raw)
            if (not isinstance(value, dict) or value.get('format') != 'FolderHubPreferences'
                    or value.get('version') != 1):
                raise PreferenceError('个性化设置文件格式不兼容')
            return validate(value.get('settings'))
        except (OSError, UnicodeError, ValueError) as exc:
            if isinstance(exc, PreferenceError):
                raise
            raise PreferenceError('个性化设置文件损坏，请检查 data/preferences.json') from exc

    def get(self):
        with self._lock:
            settings = self._read()
            return {'configured': settings is not None, 'settings': settings or dict(DEFAULTS)}

    def _write(self, settings):
        data = json.dumps({'format': 'FolderHubPreferences', 'version': 1, 'settings': settings},
                          ensure_ascii=False, indent=2).encode('utf-8') + b'\n'
        if len(data) > MAX_BYTES:
            raise PreferenceError('个性化设置文件过大')
        temporary = None
        try:
            with tempfile.NamedTemporaryFile('wb', dir=self.path.parent, prefix='.preferences-',
                                             suffix='.tmp', delete=False) as output:
                temporary = Path(output.name)
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return settings

    def save(self, settings, *, only_if_missing=False):
        with self._lock:
            if only_if_missing:
                existing = self._read()
                if existing is not None:
                    return {'configured': True, 'settings': existing, 'imported': False}
            checked = validate(settings)
            self._write(checked)
            return {'configured': True, 'settings': checked, 'imported': only_if_missing}

    def snapshot_bytes(self):
        """Give portable backups a valid complete settings file, even before first browser visit."""
        with self._lock:
            settings = self._read()
            if settings is None:
                settings = dict(DEFAULTS)
            return (json.dumps({'format': 'FolderHubPreferences', 'version': 1, 'settings': settings},
                               ensure_ascii=False, indent=2) + '\n').encode('utf-8')
