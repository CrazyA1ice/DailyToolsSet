"""Portable, atomic and validated FolderHub presentation preferences."""
from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import tempfile
from urllib.parse import urlsplit
from threading import RLock

DEFAULTS = {
    'font': 'large', 'density': 'comfortable', 'listDensity': 'normal', 'sidebar': 'normal',
    'columns': 'auto', 'accent': 'blue', 'showCovers': True,
    'coverHeight': 'normal', 'coverFit': 'cover', 'sidebarCollapsed': False,
    'theme': 'cloud', 'layout': 'grid', 'expanded': None, 'savedViews': [], 'folderGroups': [], 'workspaces': [],
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
MAX_WORKSPACES = 20
MAX_WORKSPACE_MEMBERS = 30
MAX_WORKSPACE_DESCRIPTION = 240
WORKSPACE_STATUSES = frozenset(('planning', 'active', 'paused', 'done'))
MAX_WORKSPACE_LINKS = 8
MAX_WORKSPACE_LINK_TITLE = 60
MAX_WORKSPACE_LINK_URL = 2048
MAX_BYTES = 128 * 1024


class PreferenceError(ValueError):
    pass


class PreferenceConflict(PreferenceError):
    """A browser tried to replace settings based on an obsolete revision."""


_UNSET = object()


def settings_revision(settings):
    if settings is None:
        return None
    canonical = json.dumps(settings, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return 'sha256:' + hashlib.sha256(canonical.encode('utf-8')).hexdigest()


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


def validate_workspace_links(value):
    """Only human-entered HTTP(S) references; never local paths or executable URLs."""
    if not isinstance(value, list) or len(value) > MAX_WORKSPACE_LINKS:
        raise PreferenceError('每个工作区最多保存 8 条资源链接')
    result, urls = [], set()
    for link in value:
        if not isinstance(link, dict) or set(link) != {'name', 'url'}:
            raise PreferenceError('工作区资源链接字段无效')
        name, url = link['name'], link['url']
        if (not isinstance(name, str) or name != name.strip() or not 1 <= len(name) <= MAX_WORKSPACE_LINK_TITLE
                or any(ord(c) < 32 or ord(c) == 127 for c in name)):
            raise PreferenceError('资源名称必须为 1—60 字且不包含控制字符')
        if (not isinstance(url, str) or not 1 <= len(url) <= MAX_WORKSPACE_LINK_URL
                or any(ord(c) <= 32 or ord(c) == 127 or c == '\\' for c in url)):
            raise PreferenceError('资源链接不能包含空白、控制字符或反斜杠')
        try:
            parsed = urlsplit(url)
            valid = (parsed.scheme.lower() in ('http', 'https')
                     and url.lower().startswith(parsed.scheme.lower() + '://')
                     and bool(parsed.hostname) and bool(parsed.netloc)
                     and parsed.username is None and parsed.password is None
                     and not parsed.netloc.endswith(':')
                     and (parsed.port is None or 1 <= parsed.port <= 65535))
        except ValueError:
            valid = False
        if not valid:
            raise PreferenceError('资源链接仅支持完整的 HTTP/HTTPS 地址，不能包含账号密码')
        if url.casefold() in urls:
            raise PreferenceError('同一工作区不能添加重复的资源链接')
        urls.add(url.casefold())
        result.append({'name': name, 'url': url})
    return result


def validate_workspaces(value):
    """Workspaces contain module IDs and optional safe browser links, never executable paths.

    The new status/links keys are optional so existing V4.1/V4.2 files remain
    valid and the legacy shape stays unchanged until the user edits a workspace.
    """
    if not isinstance(value, list) or len(value) > MAX_WORKSPACES:
        raise PreferenceError('项目工作区最多保存 20 个')
    result, used_names = [], set()
    allowed = {'name', 'description', 'members', 'status', 'links', 'launch_ids'}
    required = {'name', 'description', 'members'}
    for workspace in value:
        if (not isinstance(workspace, dict) or not required.issubset(workspace)
                or set(workspace) - allowed):
            raise PreferenceError('项目工作区字段无效')
        name, description, members = (
            workspace['name'], workspace['description'], workspace['members'])
        if (not isinstance(name, str) or name != name.strip()
                or not 1 <= len(name) <= 40
                or any(ord(ch) < 32 or ord(ch) == 127 for ch in name)):
            raise PreferenceError('项目工作区名称需为 1—40 字且不能包含控制字符')
        if name.casefold() in used_names:
            raise PreferenceError('项目工作区名称不可重复')
        used_names.add(name.casefold())
        if (not isinstance(description, str) or len(description) > MAX_WORKSPACE_DESCRIPTION
                or any((ord(ch) < 32 and ch != '\n') or ord(ch) == 127
                       for ch in description)):
            raise PreferenceError('工作区说明不得超过 240 字或包含控制字符')
        if (not isinstance(members, list) or not 1 <= len(members) <= MAX_WORKSPACE_MEMBERS
                or any(type(node_id) is not int or node_id < 1 for node_id in members)
                or len(set(members)) != len(members)):
            raise PreferenceError('工作区需关联 1—30 个不重复的模块 ID')
        item = {'name': name, 'description': description, 'members': members[:]}
        if 'status' in workspace:
            status = workspace['status']
            if type(status) is not str or status not in WORKSPACE_STATUSES:
                raise PreferenceError('项目状态必须为筹备中、进行中、已暂停或已完成')
            item['status'] = status
        if 'links' in workspace:
            item['links'] = validate_workspace_links(workspace['links'])
        if 'launch_ids' in workspace:
            launch_ids = workspace['launch_ids']
            if (not isinstance(launch_ids, list) or len(launch_ids) > 8
                    or any(type(node_id) is not int or node_id < 1 for node_id in launch_ids)
                    or len(set(launch_ids)) != len(launch_ids)
                    or not set(launch_ids).issubset(members)
                    or [node_id for node_id in members if node_id in launch_ids] != launch_ids):
                raise PreferenceError('启动清单必须是工作区成员中的至多8个不重复模块，顺序需与成员一致')
            item['launch_ids'] = launch_ids[:]
        result.append(item)
    return result


def validate(value):
    """Validate a complete/partial settings object without coercing or trusting unknown keys."""
    if not isinstance(value, dict) or set(value) - set(DEFAULTS):
        raise PreferenceError('个性化设置格式或字段无效')
    result = {**DEFAULTS, 'savedViews': [], 'folderGroups': [], 'workspaces': []}
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
        elif key == 'workspaces':
            item = validate_workspaces(item)
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
                    'revision': settings_revision(settings),
                    'settings': settings if settings is not None else {**DEFAULTS, 'savedViews': [], 'folderGroups': [], 'workspaces': []}}

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

    def save(self, settings, *, only_if_missing=False, expected_revision=_UNSET):
        with self._lock:
            # Compare against the current on-disk content inside the same lock
            # as the atomic replace. Omitted revision keeps older API callers
            # compatible; browser clients send the revision explicitly.
            existing = self._read()
            if only_if_missing and existing is not None:
                return {'configured': True, 'settings': existing,
                        'revision': settings_revision(existing), 'imported': False}
            if expected_revision is not _UNSET and not only_if_missing:
                if (expected_revision is not None and
                        (type(expected_revision) is not str or len(expected_revision) != 71
                         or not expected_revision.startswith('sha256:')
                         or any(c not in '0123456789abcdef' for c in expected_revision[7:]))):
                    raise PreferenceError('个性化设置版本格式无效')
                if expected_revision != settings_revision(existing):
                    raise PreferenceConflict('其他页面已修改个性化设置；已拒绝旧版本覆盖，请记录本页尚未保存的内容并刷新后重试')
            checked = validate(settings)
            self._write(checked)
            return {'configured': True, 'settings': checked,
                    'revision': settings_revision(checked), 'imported': only_if_missing}

    def snapshot_bytes(self):
        """Give portable backups a valid complete settings file, even before first browser visit."""
        with self._lock:
            settings = self._read()
            if settings is None:
                settings = {**DEFAULTS, 'savedViews': [], 'folderGroups': [], 'workspaces': []}
            return (json.dumps({'format': 'FolderHubPreferences', 'version': 1, 'settings': settings},
                               ensure_ascii=False, indent=2) + '\n').encode('utf-8')
