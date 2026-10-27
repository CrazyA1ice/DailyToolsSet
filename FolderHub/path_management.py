"""Safe, preview-first Windows folder path diagnostics and prefix remapping.

Never modifies real directories: only the `folder_path` SQLite column is updated.
"""
from __future__ import annotations

import hashlib
import json
import ntpath
import os
import re
from datetime import datetime, timezone

MAX_PATH_CHECK = 1000
MAX_REMAP = 1000
MAX_SUGGEST_CANDIDATES = 12
MAX_SUGGEST_PROBES = 24
MAX_SUGGEST_RESULTS = 5
MAX_SUGGEST_DEPTH = 6


class PathRuleError(ValueError):
    """Expected invalid input or stale preview; safe to display to the user."""


def normalize_prefix(value):
    """Only accept fully qualified Windows drive/UNC folder prefixes.

    Strip redundant separators and normalize `.`, but reject `..` in the
    supplied prefix to prevent an accidental match of the wrong subtree.
    """
    if not isinstance(value, str):
        raise PathRuleError("路径前缀必须是文本")
    raw = value.strip().strip('"').replace('/', '\\')
    if (not raw or len(raw) > 2048 or any(c in raw for c in '\0\r\n')
            or raw.startswith(('\\\\?\\', '\\\\.\\'))):
        raise PathRuleError("请输入有效的 Windows 盘符或 UNC 共享目录路径")
    parts = raw.split('\\')
    if '..' in parts:
        raise PathRuleError("批量替换前缀不允许包含上级目录 '..'")
    drive, tail = ntpath.splitdrive(raw)
    if not ntpath.isabs(raw) or not drive:
        raise PathRuleError("路径必须是绝对 Windows 路径，例如 D:\\Work 或 E:\\")
    if re.fullmatch(r'[A-Za-z]:', drive):
        pass
    elif not (drive.startswith('\\\\') and len(drive.split('\\')) >= 4 and
              all(drive.split('\\')[2:4])):
        raise PathRuleError("UNC 路径需包含服务器名与共享名")
    normalized = ntpath.normpath(raw)
    if not ntpath.isabs(normalized):
        raise PathRuleError("路径前缀无效")
    return normalized


def replaced_path(original, source, target):
    """Replace a whole Windows directory prefix, never a partial name match."""
    # Old records may contain mixed slash forms. Never modify paths without a
    # drive-qualified source prefix match.
    candidate = ntpath.normpath(original.replace('/', '\\'))
    source_base = source.rstrip('\\')
    target_base = target.rstrip('\\')
    folded = ntpath.normcase(candidate)
    if folded == ntpath.normcase(source):
        return target
    boundary = ntpath.normcase(source_base + '\\')
    if folded.startswith(boundary):
        result = ntpath.normpath(target_base + candidate[len(source_base):])
        if len(result) > 2048:
            raise PathRuleError("替换后的文件夹路径过长")
        return result
    return None


def _plan(db, source, target):
    if ntpath.normcase(source) == ntpath.normcase(target):
        raise PathRuleError("新旧路径相同，无需修改")
    rows = db.execute("SELECT id,title,folder_path FROM nodes WHERE folder_path IS NOT NULL AND folder_path != '' ORDER BY id").fetchall()
    changes = []
    for row in rows:
        updated = replaced_path(row['folder_path'], source, target)
        if updated is not None:
            changes.append({'id': row['id'], 'title': row['title'], 'old_path': row['folder_path'], 'new_path': updated})
            if len(changes) > MAX_REMAP:
                raise PathRuleError(f"匹配超过 {MAX_REMAP} 个模块，请使用更精确的旧目录前缀")
    signature = [(r['id'], r['old_path'], r['new_path']) for r in changes]
    digest = hashlib.sha256(json.dumps(signature, ensure_ascii=False, separators=(',', ':')).encode('utf-8')).hexdigest()
    return {'count': len(changes), 'changes': changes, 'fingerprint': digest}


def preview(store, source, target):
    source, target = normalize_prefix(source), normalize_prefix(target)
    with store.connect() as db:
        return {'source': source, 'target': target, **_plan(db, source, target)}


def apply(store, source, target, fingerprint):
    if not isinstance(fingerprint, str) or not re.fullmatch(r'[a-f0-9]{64}', fingerprint):
        raise PathRuleError("请先生成并确认有效的替换预览")
    source, target = normalize_prefix(source), normalize_prefix(target)
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        plan = _plan(db, source, target)
        if not plan['count'] or fingerprint != plan['fingerprint']:
            raise PathRuleError("预览已过期或路径已变化，请重新生成预览，避免覆盖新修改")
        stamped = datetime.now(timezone.utc).isoformat(timespec='seconds')
        for entry in plan['changes']:
            result = db.execute('UPDATE nodes SET folder_path=?,updated_at=? WHERE id=? AND folder_path=?',
                                (entry['new_path'], stamped, entry['id'], entry['old_path']))
            if result.rowcount != 1:
                raise PathRuleError("模块路径同时被修改，请重新生成预览")
    return {'ok': True, 'changed': plan['count']}



def suggest_migrations(store, target, exists_fn=None):
    """Infer plausible old directory prefixes for an explicitly chosen new root.

    This is an opt-in *read-only* diagnostic, not a filesystem crawler.
    It visits at most 1000 saved folder records and performs at most
    12 x 24 bounded directory checks (plus a single new-root check).
    No results are persisted. All suggested rewrites must go through the
    existing fingerprinted preview/apply workflow.
    """
    target = normalize_prefix(target)
    if exists_fn is None:
        if os.name != 'nt':
            raise PathRuleError("智能路径建议需在 Windows 本机运行")
        exists_fn = os.path.isdir

    with store.connect() as db:
        rows = db.execute(
            "SELECT id,title,folder_path FROM nodes WHERE folder_path IS NOT NULL AND folder_path != '' ORDER BY id LIMIT ?",
            (MAX_PATH_CHECK + 1,),
        ).fetchall()
    if len(rows) > MAX_PATH_CHECK:
        raise PathRuleError(f"关联路径超过 {MAX_PATH_CHECK} 条，无法安全推断建议")

    def accessible(path):
        try:
            return bool(exists_fn(path))
        except (OSError, ValueError):
            return False

    if not accessible(target):
        raise PathRuleError("指定的新根目录无法访问，请确认它存在且当前用户有权限")

    groups = {}
    for row in rows:
        try:
            original = normalize_prefix(row['folder_path'])
        except PathRuleError:
            continue  # Historical or non-Windows paths are never guessed.
        parent = ntpath.dirname(original)
        for _ in range(MAX_SUGGEST_DEPTH):
            if not parent or ntpath.normcase(parent) == ntpath.normcase(original):
                break  # Do not guess exact-record replacements.
            key = ntpath.normcase(parent)
            group = groups.setdefault(key, {'source': parent, 'rows': []})
            group['rows'].append(row)
            upper = ntpath.dirname(parent)
            if upper == parent:
                break
            parent = upper

    ranked_groups = sorted(groups.values(),
                           key=lambda g: (-len(g['rows']), -len(g['source']),
                                          ntpath.normcase(g['source'])))
    suggestions, cache = [], {}
    for group in ranked_groups[:MAX_SUGGEST_CANDIDATES]:
        source = group['source']
        if ntpath.normcase(source) == ntpath.normcase(target):
            continue
        samples = []
        for row in group['rows'][:MAX_SUGGEST_PROBES]:
            proposed = replaced_path(row['folder_path'], source, target)
            if proposed is None or ntpath.normcase(proposed) == ntpath.normcase(row['folder_path']):
                continue
            key = ntpath.normcase(proposed)
            if key not in cache:
                cache[key] = accessible(proposed)
            samples.append({'id': row['id'], 'title': row['title'],
                            'old_path': row['folder_path'],
                            'new_path': proposed, 'exists': cache[key]})
        verified = sum(item['exists'] for item in samples)
        if not verified:
            continue  # Never recommend a mapping without any positive path evidence.
        suggestions.append({
            'source': source, 'target': target, 'linked': len(group['rows']),
            'checked': len(samples), 'verified': verified,
            'examples': samples[:3],
        })
    suggestions.sort(key=lambda item: (-item['verified'], -item['linked'],
                                       -(item['verified'] / max(item['checked'], 1)),
                                       -len(item['source']), ntpath.normcase(item['source'])))
    return {'target': target, 'total': len(rows),
            'suggestions': suggestions[:MAX_SUGGEST_RESULTS],
            'sample_limit': MAX_SUGGEST_PROBES}

def check_health(store, exists_fn=None):
    """Manually triggered, non-recursive directory existence checks.

    A network drive may be slow; this is intentionally never run on homepage
    load or in a recurring background task.
    """
    if exists_fn is None:
        if os.name != 'nt':
            raise PathRuleError("关联文件夹检测需在 Windows 本机运行")
        exists_fn = os.path.isdir
    with store.connect() as db:
        rows = db.execute("SELECT id,title,folder_path FROM nodes WHERE folder_path IS NOT NULL AND folder_path != '' ORDER BY id LIMIT ?", (MAX_PATH_CHECK + 1,)).fetchall()
    if len(rows) > MAX_PATH_CHECK:
        raise PathRuleError(f"关联路径超过 {MAX_PATH_CHECK} 条，请先缩小目录规模后分批检测")
    checks = []
    for row in rows:
        try:
            exists = bool(exists_fn(row['folder_path']))
        except (OSError, ValueError):
            exists = False
        checks.append({'id': row['id'], 'title': row['title'], 'path': row['folder_path'], 'exists': exists})
    return {'total': len(checks), 'accessible': sum(c['exists'] for c in checks),
            'missing': sum(not c['exists'] for c in checks), 'items': checks}
