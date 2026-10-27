"""Portable, atomic and validated FolderHub presentation preferences."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from threading import RLock

DEFAULTS = {
    'font': 'large', 'density': 'comfortable', 'listDensity': 'normal', 'sidebar': 'normal',
    'columns': 'auto', 'accent': 'blue', 'showCovers': True,
    'coverHeight': 'normal', 'coverFit': 'cover', 'sidebarCollapsed': False,
    'theme': 'cloud', 'layout': 'grid', 'expanded': None, 'savedViews': [], 'folderGroups': [],
}
CHOICES = {
    'font': ('normal', 'large', 'xlarge'),
    'density': ('comfortable', 'compact'),
    'listDensity': ('compact', 'normal', 'relaxed'),
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
MAX_SAVED_VIEWS = 24
MAX_SMART_TAGS = 30
MAX_FOLDER_GROUPS = 20
MAX_GROUP_MEMBERS = 8
MAX_BYTES = 128 * 1024


class PreferenceError(ValueError):
    pass


def validate_saved_views(value):
    if not isinstance(value, list) or len(value) > MAX_SAVED_VIEWS:
        raise PreferenceError('智能收藏夹最多保存 24 个')
    result, used_names = [], set()
    for entry in value:
        if not isinstance(entry, dict) or set(entry) != {'name', 'includes', 'excludes', 'mode'}:
            raise PreferenceError('智能收藏夹字段无效')
        name = entry['name']
        if (not isinstance(name, str) or not 1 <= len(name.strip()) <= 40
                or name != name.strip() or any(ord(c) < 32 or ord(c) == 127 for c in name)):
            raise PreferenceError('智能收藏夹名称无效（最多 40 字）')
        key = name.casefold()
        if key in used_names:
            raise PreferenceError('智能收藏夹名称不能重复')
        used_names.add(key)
        if entry['mode'] not in ('any', 'all') or type(entry['mode']) is not str:
            raise PreferenceError('智能收藏夹匹配方式无效')
        selections = []
        for kind in ('includes', 'excludes'):
            tags = entry[kind]
            if (not isinstance(tags, list) or len(tags) > MAX_SMART_TAGS
                    or any(not isinstance(tag, str) or not 1 <= len(tag) <= 24
                           or tag != tag.strip()
                           or any(c in tag for c in ',，;；')
                           or any(ord(c) < 32 or ord(c) == 127 for c in tag)
                           for tag in tags)
                    or len({tag.casefold() for tag in tags}) != len(tags)):
                raise PreferenceError('智能收藏夹标签无效')
            selections.append(tags[:])
        if not (selections[0] or selections[1]):
            raise PreferenceError('智能收藏夹至少包含一个筛选条件')
        if {tag.casefold() for tag in selections[0]} & {tag.casefold() for tag in selections[1]}:
            raise PreferenceError('同一标签不能同时包含和排除')
        result.append({'name': name, 'includes': selections[0],
                       'excludes': selections[1], 'mode': entry['mode']})
    return result


def validate_folder_groups(value):
    """Portable folder-group definitions store only node IDs, never raw paths."""
    if not isinstance(value, list) or len(value) > MAX_FOLDER_GROUPS:
        raise PreferenceError('最多保存 20 个文件夹工作组')
    result, names = [], set()
    for group in value:
        if not isinstance(group, dict) or set(group) != {'name', 'members'}:
            raise PreferenceError('文件夹组结构无效')
        name, members = group['name'], group['members']
        if (not isinstance(name, str) or name != name.strip()
                or not 1 <= len(name) <= 40
                or any(ord(ch) < 32 or ord(ch) == 127 for ch in name)):
            raise PreferenceError('文件夹组名称须为 1—40 字，不能包含控制字符')
        if name.casefold() in names:
            raise PreferenceError('文件夹组名称不能重复')
        names.add(name.casefold())
        if (not isinstance(members, list) or not 2 <= len(members) <= MAX_GROUP_MEMBERS
                or any(type(node_id) is not int or node_id < 1 for node_id in members)
                or len(members) != len(set(members))):
            raise PreferenceError('文件夹组须包含 2—8 个不重复的有效模块 ID')
        result.append({'name': name, 'members': members[:]})
    return result


def validate(value):
    """Validate a complete/partial settings object without coercing or trusting unknown keys."""
    if not isinstance(value, dict) or set(value) - set(DEFAULTS):
        raise PreferenceError('个性化设置格式或字段无效')
    result = {**DEFAULTS, 'savedViews': [], 'folderGroups': []}
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
        elif key == 'savedViews':
            item = validate_saved_views(item)
        elif key == 'folderGroups':
            item = validate_folder_groups(item)
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
            return {'configured': settings is not None,
                    'settings': settings if settings is not None else {**DEFAULTS, 'savedViews': [], 'folderGroups': []}}

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
                settings = {**DEFAULTS, 'savedViews': [], 'folderGroups': []}
            return (json.dumps({'format': 'FolderHubPreferences', 'version': 1, 'settings': settings},
                               ensure_ascii=False, indent=2) + '\n').encode('utf-8')
